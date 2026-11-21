import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Proof, VerificationLink, Confirmation, EvidenceRecord, utcnow
from ..services.matcher import match
from ..services.report import build_report
from ..services import evidence
from .proofs import to_paise

router = APIRouter(prefix="/api/v", tags=["verify"])


def get_link(db, token):
    link = db.query(VerificationLink).filter_by(token=token).first()
    if not link:
        raise HTTPException(404, "This verification link does not exist")
    return link


@router.get("/{token}")
def open_link(token: str, db: Session = Depends(get_db)):
    """Blind page: shows who is asking, never the claimed values."""
    link = get_link(db, token)
    proof = db.get(Proof, link.proof_id)
    if link.opened_at is None:
        link.opened_at = utcnow()
        db.commit()
    expired = link.expires_at is not None and utcnow() > link.expires_at
    record_id = None
    if link.status == "confirmed":
        rec = db.query(EvidenceRecord).filter_by(proof_id=proof.id).order_by(EvidenceRecord.seq.desc()).first()
        record_id = rec.id if rec else None
    return {"worker_name": proof.worker_name, "status": link.status, "expired": expired, "record_id": record_id}


class ConfirmIn(BaseModel):
    amount: str
    utr: Optional[str] = None
    paid_at: Optional[datetime.datetime] = None


@router.post("/{token}/confirm")
def confirm(token: str, body: ConfirmIn, db: Session = Depends(get_db)):
    link = get_link(db, token)
    if link.status == "confirmed":
        raise HTTPException(409, "This link has already been used")
    if link.expires_at and utcnow() > link.expires_at:
        raise HTTPException(410, "This link has expired")
    proof = db.get(Proof, link.proof_id)

    utr = (body.utr or "").strip().replace(" ", "") or None
    conf = Confirmation(link_id=link.id, amount_paise=to_paise(body.amount), utr=utr, paid_at=body.paid_at)
    db.add(conf)
    link.status = "confirmed"
    db.commit()

    verdict, diff = match(proof, conf)
    rec = evidence.create_record(db, proof, link, conf, verdict, diff, build_report(proof, db))
    return {"record_id": rec.id, "verdict": verdict}
