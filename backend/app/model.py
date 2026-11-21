import uuid
import datetime
from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, JSON, ForeignKey
from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class Proof(Base):
    """One uploaded payment proof plus the fields the worker confirmed."""
    __tablename__ = "proofs"
    id = Column(String, primary_key=True, default=new_id)
    worker_name = Column(String)
    worker_phone = Column(String, index=True)
    file_key = Column(String, nullable=False)       # path of untouched original
    file_name = Column(String)
    file_type = Column(String)                      # png / jpg / webp / pdf / txt
    file_sha256 = Column(String(64), nullable=False, index=True)
    phash = Column(String(16), index=True)
    amount_paise = Column(BigInteger)
    utr = Column(String(12), index=True)
    paid_at = Column(DateTime)
    payer_upi = Column(String)
    payee_upi = Column(String)
    app_name = Column(String)
    ocr_confidence = Column(Float)
    file_findings = Column(JSON, default=list)      # findings from file analysis
    created_at = Column(DateTime, default=utcnow)


class VerificationLink(Base):
    __tablename__ = "verification_links"
    id = Column(String, primary_key=True, default=new_id)
    proof_id = Column(String, ForeignKey("proofs.id"), index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime)
    opened_at = Column(DateTime)
    status = Column(String, default="pending")      # pending / confirmed


class Confirmation(Base):
    """What the counterparty typed in, blind."""
    __tablename__ = "confirmations"
    id = Column(String, primary_key=True, default=new_id)
    link_id = Column(String, ForeignKey("verification_links.id"), index=True)
    amount_paise = Column(BigInteger)
    utr = Column(String(12))
    paid_at = Column(DateTime)
    submitted_at = Column(DateTime, default=utcnow)


class EvidenceRecord(Base):
    """Append-only, hash-chained evidence record. Never update rows in this table."""
    __tablename__ = "evidence_records"
    id = Column(String, primary_key=True)
    seq = Column(Integer, unique=True, nullable=False)
    proof_id = Column(String, ForeignKey("proofs.id"), index=True)
    verdict = Column(String)                        # matched / partial / mismatch / unconfirmed
    payload = Column(JSON)                          # everything that is hashed
    pdf_key = Column(String)
    pdf_sha256 = Column(String(64), index=True)
    prev_hash = Column(String(64))
    record_hash = Column(String(64))
    signature = Column(String(64))                  # server HMAC over hash + timestamp
    created_at = Column(DateTime, default=utcnow)
