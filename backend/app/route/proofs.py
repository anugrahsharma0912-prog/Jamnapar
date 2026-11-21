import os
import secrets
import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR, MAX_UPLOAD_BYTES, LINK_TTL_DAYS
from ..db import get_db
from ..models import Proof, VerificationLink, EvidenceRecord, new_id, utcnow
from ..services import forensics, ocr
from ..services.hashing import sha256_bytes, perceptual_hash
from ..services.report import build_report

router = APIRouter(prefix="/api/proofs", tags=["proofs"])

ALLOWED = {"png": "png", "jpg": "jpg", "jpeg": "jpg", "webp": "webp", "pdf": "pdf", "txt": "txt"}


def to_paise(value) -> int:
    try:
        return int((Decimal(str(value).replace(",", "")) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "Amount must be a number")


def get_proof(db: Session, proof_id: str) -> Proof:
    p = db.get(Proof, proof_id)
    if not p:
        raise HTTPException(404, "Proof not found")
    return p


def proof_out(p: Proof, db: Session) -> dict:
    link = db.query(VerificationLink).filter_by(proof_id=p.id).first()
    records = db.query(EvidenceRecord).filter_by(proof_id=p.id).order_by(EvidenceRecord.seq).all()
    return {
        "id": p.id, "worker_name": p.worker_name, "file_name": p.file_name, "file_type": p.file_type,
        "file_sha256": p.file_sha256, "created_at": p.created_at.isoformat() + "Z",
        "fields": {
            "amount": None if p.amount_paise is None else f"{p.amount_paise / 100:.2f}",
            "utr": p.utr,
            "paid_at": p.paid_at.isoformat(timespec="minutes") if p.paid_at else None,
            "payer_upi": p.payer_upi, "payee_upi": p.payee_upi, "app_name": p.app_name,
        },
        "report": build_report(p, db),
        "link": None if not link else {
            "token": link.token, "path": f"/v/{link.token}", "status": link.status,
            "opened_at": link.opened_at.isoformat() + "Z" if link.opened_at else None,
            "expires_at": link.expires_at.isoformat() + "Z" if link.expires_at else None,
        },
        "records": [{"id": r.id, "verdict": r.verdict, "created_at": r.created_at.isoformat() + "Z"} for r in records],
    }


@router.post("")
async def upload_proof(file: UploadFile = File(...), worker_name: str = Form(...), worker_phone: str = Form(...),
                       db: Session = Depends(get_db)):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "Upload a PNG, JPG, WEBP, PDF or TXT (SMS text) file")
    data = await file.read()
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is empty or larger than 10 MB")
    ftype = ALLOWED[ext]
    if ftype in ("png", "jpg", "webp"):
        try:
            from PIL import Image
            import io
            Image.open(io.BytesIO(data)).verify()
        except Exception:
            raise HTTPException(400, "That file is not a valid image")

    pid = new_id()
    key = os.path.join(UPLOAD_DIR, f"{pid}.{ftype}")
    with open(key, "wb") as f:
        f.write(data)  # the untouched original

    ex = ocr.extract_fields(data, ftype)
    proof = Proof(
        id=pid, worker_name=worker_name.strip(), worker_phone=worker_phone.strip(),
        file_key=key, file_name=file.filename, file_type=ftype,
        file_sha256=sha256_bytes(data), phash=perceptual_hash(data) if ftype in ("png", "jpg", "webp") else None,
        amount_paise=ex["amount_paise"], utr=ex["utr"], paid_at=ex["paid_at"],
        payer_upi=ex["payer_upi"], payee_upi=ex["payee_upi"], app_name=ex["app_name"],
        file_findings=forensics.analyze_file(data, ftype),
    )
    db.add(proof)
    db.commit()
    out = proof_out(proof, db)
    out["ocr_ok"] = ex["ocr_ok"]
    return out


@router.get("/{proof_id}")
def read_proof(proof_id: str, db: Session = Depends(get_db)):
    return proof_out(get_proof(db, proof_id), db)


@router.get("/{proof_id}/file")
def read_file(proof_id: str, db: Session = Depends(get_db)):
    p = get_proof(db, proof_id)
    return FileResponse(p.file_key, filename=p.file_name)


class FieldsIn(BaseModel):
    amount: Optional[str] = None
    utr: Optional[str] = None
    paid_at: Optional[datetime.datetime] = None
    payer_upi: Optional[str] = None
    payee_upi: Optional[str] = None
    app_name: Optional[str] = None


@router.patch("/{proof_id}/fields")
def update_fields(proof_id: str, body: FieldsIn, db: Session = Depends(get_db)):
    p = get_proof(db, proof_id)
    if db.query(VerificationLink).filter_by(proof_id=p.id).first():
        raise HTTPException(409, "The claim is locked once a verification link has been created.")
    data = body.model_dump(exclude_unset=True)
    if "amount" in data:
        p.amount_paise = to_paise(data["amount"]) if data["amount"] not in (None, "") else None
    if "utr" in data:
        p.utr = (data["utr"] or "").strip().replace(" ", "") or None
    for k in ("paid_at", "payer_upi", "payee_upi", "app_name"):
        if k in data:
            setattr(p, k, data[k] or None)
    db.commit()
    return proof_out(p, db)


@router.post("/{proof_id}/link")
def create_link(proof_id: str, db: Session = Depends(get_db)):
    p = get_proof(db, proof_id)
    existing = db.query(VerificationLink).filter_by(proof_id=p.id).first()
    if existing:
        return proof_out(p, db)
    if p.amount_paise is None:
        raise HTTPException(400, "Enter the amount before creating a link.")
    link = VerificationLink(proof_id=p.id, token=secrets.token_urlsafe(24),
                            expires_at=utcnow() + datetime.timedelta(days=LINK_TTL_DAYS))
    db.add(link)
    db.commit()
    return proof_out(p, db)
