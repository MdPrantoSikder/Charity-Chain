from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx, os, logging, time

from database import get_db
from models import User, AuditLog
from routes.auth import get_current_user

logger = logging.getLogger("CharityChain")
router = APIRouter(prefix="/api/payment", tags=["payment"])

STORE_ID       = os.getenv("SSLCOMMERZ_STORE_ID")
STORE_PASSWORD = os.getenv("SSLCOMMERZ_STORE_PASSWORD")
SESSION_API    = os.getenv("SSLCOMMERZ_SESSION_API")
VALIDATION_API = os.getenv("SSLCOMMERZ_VALIDATION_API")
BACKEND_URL    = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
FRONTEND_URL   = os.getenv("FRONTEND_URL", "http://127.0.0.1:5500/frontend")


@router.post("/initiate")
async def initiate_payment(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    body = await request.json()
    amount = float(body.get("amount", 0))

    if amount < 1:
        return JSONResponse({"error": "Minimum amount is 1 BDT"}, status_code=400)

    payload = {
        "store_id":        STORE_ID,
        "store_passwd":    STORE_PASSWORD,
        "total_amount":    amount,
        "currency":        "BDT",
        "tran_id":         f"TOPUP_{current_user.id}_{int(time.time())}",
        "success_url":     f"{BACKEND_URL}/api/payment/success",
        "fail_url":        f"{BACKEND_URL}/api/payment/fail",
        "cancel_url":      f"{BACKEND_URL}/api/payment/cancel",
        "cus_name":        current_user.full_name or "Donor",
        "cus_email":       current_user.email,
        "cus_phone":       "01700000000",
        "cus_add1":        "Dhaka",
        "cus_city":        "Dhaka",
        "cus_country":     "Bangladesh",
        "shipping_method": "NO",
        "product_name":    "Wallet Top Up",
        "product_category":"Service",
        "product_profile": "general",
        "value_a":         str(current_user.id),
        "value_b":         str(amount),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(SESSION_API, data=payload, timeout=30)
        data = resp.json()

    if data.get("status") == "SUCCESS":
        return {"redirect_url": data["GatewayPageURL"]}
    else:
        logger.error(f"SSLCommerz error: {data}")
        return JSONResponse({"error": data.get("failedreason", "Payment initiation failed")}, status_code=400)


@router.post("/success")
async def payment_success(request: Request, db: AsyncSession = Depends(get_db)):
    """
    SECURITY: this endpoint is publicly reachable, so nothing posted to it can be
    trusted. Three rules are enforced here:

      1. ALWAYS call the SSLCommerz Validation API. The old code skipped
         validation whenever the POSTed status already said VALID -- so anyone
         could POST status=VALID&amount=999999&value_a=<id> and top up a wallet
         for free.
      2. Take the amount from the VALIDATION RESPONSE, never from the form.
      3. Reject a tran_id that was already credited (idempotency), so a refresh
         or a duplicate IPN cannot double-credit.
    """
    form    = await request.form()
    val_id  = form.get("val_id", "")
    tran_id = form.get("tran_id", "")
    user_id = form.get("value_a", "")

    if not val_id or not tran_id:
        logger.warning("Payment callback missing val_id or tran_id")
        return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

    # 1. Always validate, outbound, against SSLCommerz itself
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(VALIDATION_API, params={
                "val_id":       val_id,
                "store_id":     STORE_ID,
                "store_passwd": STORE_PASSWORD,
                "format":       "json"
            }, timeout=30)
            vdata = resp.json()
    except Exception as e:
        logger.error(f"Validation API unreachable: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

    if vdata.get("status") not in ("VALID", "VALIDATED"):
        logger.warning(f"Rejected payment {tran_id}: validation says {vdata.get('status')}")
        return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

    # The validated record must match the transaction we started
    if vdata.get("tran_id") and vdata.get("tran_id") != tran_id:
        logger.warning(f"tran_id mismatch: form {tran_id} vs validated {vdata.get('tran_id')}")
        return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

    if str(vdata.get("currency", "BDT")).upper() != "BDT":
        logger.warning(f"Rejected payment {tran_id}: currency {vdata.get('currency')}")
        return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

    # 2. Trust only the validated amount
    try:
        amount = float(vdata.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0

    if amount <= 0:
        logger.warning(f"Rejected payment {tran_id}: validated amount {amount}")
        return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

    try:
        # 3. Idempotency: has this tran_id already been credited?
        seen = await db.execute(
            select(AuditLog).where(AuditLog.tx_hash == tran_id)
        )
        if seen.scalar_one_or_none():
            logger.info(f"Duplicate callback for {tran_id} ignored")
            return RedirectResponse(
                f"{FRONTEND_URL}/donor.html?payment=success&amount={amount}",
                status_code=303
            )

        result = await db.execute(select(User).where(User.id == str(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            logger.error(f"User {user_id} not found for {tran_id}")
            return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

        user.wallet_balance = (user.wallet_balance or 0) + amount
        db.add(AuditLog(
            event_type="wallet_topup",
            description=f"SSLCommerz top up of BDT {amount}",
            tx_hash=tran_id,
            actor_id=user.id,
            meta={"val_id": val_id, "card_type": vdata.get("card_type")},
        ))
        await db.commit()
        logger.info(f"Payment success: user {user_id} topped up BDT {amount} ({tran_id})")

    except Exception as e:
        await db.rollback()
        logger.error(f"Payment success DB error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/donor.html?payment=failed", status_code=303)

    return RedirectResponse(
        f"{FRONTEND_URL}/donor.html?payment=success&amount={amount}",
        status_code=303
    )


@router.post("/fail")
async def payment_fail(request: Request):
    return RedirectResponse(
        f"{FRONTEND_URL}/donor.html?payment=failed",
        status_code=303
    )


@router.post("/cancel")
async def payment_cancel(request: Request):
    return RedirectResponse(
        f"{FRONTEND_URL}/donor.html?payment=cancelled",
        status_code=303
    )