from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import base64
from models import Case, User, AuditLog, CaseDocument

from database import get_db
from models import Case, User, AuditLog
from security import get_current_user, require_role, require_verified_role
from ipfs_client import pin_to_ipfs

router = APIRouter(prefix="/api/cases", tags=["cases"])


def case_response(c: Case, needy: User = None) -> dict:
    return {
        "id":             c.id,
        "needy_id":       c.needy_id,
        "applicant_name": needy.full_name if needy else None,
        "title":          c.title,
        "category":       c.category,
        "description":    c.description,
        "location":       c.location,
        "amount_needed":  c.amount_needed,
        "amount_funded":  c.amount_funded,
        "status":         c.status,
        "ipfs_cid":       c.ipfs_cid,
        "trustee_notes":  c.trustee_notes,
        "approved_at":    c.approved_at.isoformat() if c.approved_at else None,
        "created_at":     c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/submit")
async def submit_case(
    title:         str              = Form(...),
    category:      str              = Form(...),
    amount_needed: float            = Form(...),
    description:   str              = Form(""),
    location:      str              = Form(""),
    documents:     List[UploadFile] = File(default=[]),
    db:            AsyncSession     = Depends(get_db),
    current_user:  User             = Depends(require_role("needy"))
):
    if amount_needed <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    # Create case first
    case = Case(
        needy_id      = current_user.id,
        title         = title,
        category      = category,
        description   = description,
        location      = location,
        amount_needed = amount_needed,
    )
    db.add(case)
    await db.flush()  # get case.id without committing

    # Store documents
    ipfs_cid = None
    for doc in documents:
        content  = await doc.read()
        ipfs_cid = await pin_to_ipfs(
            content.decode(errors="ignore"), doc.filename
        )
        encoded = base64.b64encode(content).decode('utf-8')
        db.add(CaseDocument(
            case_id      = case.id,
            filename     = doc.filename,
            content_type = doc.content_type or "application/octet-stream",
            file_data    = encoded,
            ipfs_cid     = ipfs_cid,
        ))

    # Update case with IPFS CID of first doc
    if ipfs_cid:
        case.ipfs_cid = ipfs_cid

    db.add(AuditLog(
        event_type  = "case_submitted",
        description = f"Case '{title}' submitted by {current_user.full_name}",
        actor_id    = current_user.id,
    ))

    await db.commit()
    await db.refresh(case)
    return case_response(case, current_user)


@router.get("/my")
async def my_cases(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("needy"))
):
    result = await db.execute(
        select(Case).where(Case.needy_id == current_user.id)
    )
    return [case_response(c, current_user) for c in result.scalars().all()]


@router.get("/pending")
async def pending_cases(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_verified_role("trustee", "admin"))
):
    result = await db.execute(
        select(Case, User)
        .join(User, Case.needy_id == User.id)
        .where(Case.status == "pending")
    )
    rows = result.all()
    return [case_response(c, u) for c, u in rows]


@router.get("/approved")
async def approved_cases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Case, User)
        .join(User, Case.needy_id == User.id)
        .where(Case.status == "approved")
    )
    rows = result.all()
    return [case_response(c, u) for c, u in rows]


@router.get("/{case_id}")
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Case, User)
        .join(User, Case.needy_id == User.id)
        .where(Case.id == case_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    c, u = row
    return case_response(c, u)


class DecisionRequest(BaseModel):
    notes:  Optional[str] = ""
    reason: Optional[str] = ""


@router.post("/{case_id}/approve")
async def approve_case(
    case_id:      str,
    req:          DecisionRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_verified_role("trustee", "admin"))
):
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status != "pending":
        raise HTTPException(status_code=400, detail="Case is not pending")

    case.status        = "approved"
    case.trustee_notes = req.notes
    case.approved_at   = datetime.now(timezone.utc)

    db.add(AuditLog(
        event_type  = "case_approved",
        description = f"Case {case_id} approved by {current_user.full_name}",
        actor_id    = current_user.id,
    ))

    await db.commit()
    await db.refresh(case)
    return case_response(case)


@router.post("/{case_id}/reject")
async def reject_case(
    case_id:      str,
    req:          DecisionRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_verified_role("trustee", "admin"))
):
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.status        = "rejected"
    case.trustee_notes = req.reason

    db.add(AuditLog(
        event_type  = "case_rejected",
        description = f"Case {case_id} rejected: {req.reason}",
        actor_id    = current_user.id,
    ))

    await db.commit()
    return {"message": "Case rejected"}
@router.get("/{case_id}/documents")
async def get_case_documents(
    case_id: str,
    db:      AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CaseDocument).where(CaseDocument.case_id == case_id)
    )
    docs = result.scalars().all()
    return [
        {
            "id":           d.id,
            "filename":     d.filename,
            "content_type": d.content_type,
            "ipfs_cid":     d.ipfs_cid,
            "uploaded_at":  d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


@router.get("/documents/{doc_id}/view")
async def view_document(
    doc_id: str,
    db:     AsyncSession = Depends(get_db)
):
    from fastapi.responses import Response
    result = await db.execute(
        select(CaseDocument).where(CaseDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_data = base64.b64decode(doc.file_data)
    return Response(
        content     = file_data,
        media_type  = doc.content_type or "application/octet-stream",
        headers     = {"Content-Disposition": f"inline; filename={doc.filename}"}
    )