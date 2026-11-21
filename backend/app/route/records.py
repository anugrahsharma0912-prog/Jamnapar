from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Proof, VerificationLink, EvidenceRecord, utcnow
from ..services import evidence
from ..services.hashing import sha256_bytes
from ..services.report import build_report

router = APIRouter(prefix="/api", tags=["records"])


@router.post("/proofs/{proof_id}/finalize")
def finalize_unconfirmed(proof_id: str, db: Session = Depends(get_db)):
    """Worker closes the dispute file when the other party never confirms."""
    proof = db.get(Proof, proof_id)
    if not proof:
        raise HTTPException(404, "Proof not found")
    link = db.query(VerificationLink).filter_by(proof_id=proof.id).first()
    if not link:
        raise HTTPException(400, "Create and send a verification link first")
    if link.status == "confirmed":
        raise HTTPException(409, "The other party already confirmed; see the record")
    if db.query(EvidenceRecord).filter_by(proof_id=proof.id, verdict="unconfirmed").first():
        raise HTTPException(409, "An unconfirmed record already exists for this proof")
    rec = evidence.create_record(db, proof, link, None, "unconfirmed", {}, build_report(proof, db))
    return {"record_id": rec.id, "verdict": rec.verdict}


@router.get("/r/{record_id}")
def public_record(record_id: str, db: Session = Depends(get_db)):
    rec = db.get(EvidenceRecord, record_id)
    if not rec:
        raise HTTPException(404, "Record not found")
    ok, _ = evidence.verify_chain(db)
    return evidence.public_view(rec, ok)


@router.get("/r/{record_id}/pdf")
def record_pdf(record_id: str, db: Session = Depends(get_db)):
    rec = db.get(EvidenceRecord, record_id)
    if not rec:
        raise HTTPException(404, "Record not found")
    return FileResponse(rec.pdf_key, media_type="application/pdf", filename=f"jamnapar-record-{rec.id[:8]}.pdf")


@router.post("/verify-file")
async def verify_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Anyone can upload a record PDF to check it is byte-for-byte what we issued."""
    digest = sha256_bytes(await file.read())
    rec = db.query(EvidenceRecord).filter_by(pdf_sha256=digest).first()
    return {"authentic": rec is not None, "sha256": digest, "record_id": rec.id if rec else None}


@router.get("/chain")
def chain_status(db: Session = Depends(get_db)):
    ok, bad = evidence.verify_chain(db)
    return {"valid": ok, "first_broken_record": bad,
            "length": db.query(EvidenceRecord).count()}
