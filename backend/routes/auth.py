from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from database import get_db
from models import User
from security import hash_password, verify_password, create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    full_name: str
    email:     EmailStr
    password:  str
    role:      str = "donor"

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


def user_response(user: User) -> dict:
    return {
        "id":             user.id,
        "full_name":      user.full_name,
        "email":          user.email,
        "role":           user.role,
        "kyc_status":     user.kyc_status,
        "wallet_balance": user.wallet_balance,
    }


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    valid_roles = {"donor", "needy", "trustee", "admin"}
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail="Invalid role")

    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(
        full_name = req.full_name,
        email     = req.email,
        hashed_pw = hash_password(req.password),
        role      = req.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_token({"sub": user.id, "role": user.role})
    return {"access_token": token, "user": user_response(user)}


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user   = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_pw):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token({"sub": user.id, "role": user.role})
    return {"access_token": token, "user": user_response(user)}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return user_response(current_user)


class TopUpRequest(BaseModel):
    amount: float

@router.post("/topup")
async def topup(
    req: TopUpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    current_user.wallet_balance += req.amount
    await db.commit()
    await db.refresh(current_user)

    return {
        "message": f"Wallet topped up by {req.amount}",
        "wallet_balance": current_user.wallet_balance
    }