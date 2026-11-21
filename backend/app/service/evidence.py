"""Hash-chained, timestamped evidence records + PDF."""
import os
import io
import json
import hmac
import hashlib
import datetime
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from ..config import SECRET, RECORD_DIR
from ..models import EvidenceRecord, new_id, utcnow

GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(payload)).encode()).hexdigest()


def sign(record_hash: str, created_iso: str) -> str:
    return hmac.new(SECRET.encode(), f"{record_hash}|{created_iso}".encode(), hashlib.sha256).hexdigest()


def mask_upi(v):
    if not v or "@" not in v:
        return v
    name, bank = v.split("@", 1)
    return f"{name[:2]}***@{bank}"


def mask_phone(v):
    return f"******{v[-4:]}" if v and len(v) >= 4 else v


def rupees(paise):
    return None if paise is None else f"Rs {paise / 100:,.2f}"


def create_record(db, proof, link, confirmation, verdict, diff, report):
    last = db.query(EvidenceRecord).order_by(EvidenceRecord.seq.desc()).first()
    prev_hash = last.record_hash if last else GENESIS
    seq = (last.seq + 1) if last else 1
    rid = new_id()
    created = utcnow()
    created_iso = created.isoformat() + "Z"

    payload = {
        "record_id": rid,
        "seq": seq,
        "created_at": created_iso,
        "verdict": verdict,
        "proof": {
            "id": proof.id,
            "file_sha256": proof.file_sha256,
            "file_name": proof.file_name,
            "worker_name": proof.worker_name,
            "worker_phone_masked": mask_phone(proof.worker_phone),
        },
        "claim": {
            "amount_paise": proof.amount_paise, "utr": proof.utr,
            "paid_at": proof.paid_at.isoformat() if proof.paid_at else None,
            "payer_upi": proof.payer_upi, "payee_upi": proof.payee_upi, "app_name": proof.app_name,
        },
        "confirmation": None if confirmation is None else {
            "amount_paise": confirmation.amount_paise, "utr": confirmation.utr,
            "paid_at": confirmation.paid_at.isoformat() if confirmation.paid_at else None,
            "submitted_at": confirmation.submitted_at.isoformat() + "Z",
        },
        "link": None if link is None else {
            "created_at": link.created_at.isoformat() + "Z",
            "opened_at": link.opened_at.isoformat() + "Z" if link.opened_at else None,
        },
        "diff": diff,
        "forensics": report,
    }
    payload = json.loads(canonical(payload))  # normalise to plain JSON before hashing
    record_hash = compute_hash(prev_hash, payload)
    signature = sign(record_hash, created_iso)

    pdf_bytes = build_pdf(payload, prev_hash, record_hash, signature)
    pdf_key = os.path.join(RECORD_DIR, f"{rid}.pdf")
    with open(pdf_key, "wb") as f:
        f.write(pdf_bytes)

    rec = EvidenceRecord(id=rid, seq=seq, proof_id=proof.id, verdict=verdict, payload=payload,
                         pdf_key=pdf_key, pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
                         prev_hash=prev_hash, record_hash=record_hash, signature=signature, created_at=created)
    db.add(rec)
    db.commit()
    return rec


def verify_chain(db):
    prev = GENESIS
    for r in db.query(EvidenceRecord).order_by(EvidenceRecord.seq).all():
        if r.prev_hash != prev or compute_hash(prev, r.payload) != r.record_hash:
            return False, r.id
        prev = r.record_hash
    return True, None


def public_view(rec, chain_ok: bool) -> dict:
    p = json.loads(canonical(rec.payload))
    p["claim"]["payer_upi"] = mask_upi(p["claim"].get("payer_upi"))
    p["claim"]["payee_upi"] = mask_upi(p["claim"].get("payee_upi"))
    return {
        "record_id": rec.id, "seq": rec.seq, "verdict": rec.verdict,
        "created_at": p["created_at"], "payload": p,
        "pdf_sha256": rec.pdf_sha256, "prev_hash": rec.prev_hash,
        "record_hash": rec.record_hash, "signature": rec.signature,
        "chain_valid": chain_ok,
    }


def build_pdf(payload, prev_hash, record_hash, signature) -> bytes:
    ss = getSampleStyleSheet()
    mono = ParagraphStyle("mono", parent=ss["Normal"], fontName="Courier", fontSize=7.5, leading=10)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, leading=10, textColor=colors.grey)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    E = []

    E.append(Paragraph("Jamnapar - Payment Verification Record", ss["Title"]))
    E.append(Paragraph(f"Record ID: {payload['record_id']} &nbsp;|&nbsp; Created (UTC): {payload['created_at']}", ss["Normal"]))
    E.append(Spacer(1, 8))
    E.append(Paragraph(f"<b>Verdict: {escape(payload['verdict'].upper())}</b>", ss["Heading2"]))
    pr = payload["proof"]
    E.append(Paragraph(f"Worker: {escape(pr.get('worker_name') or '-')} ({pr.get('worker_phone_masked') or '-'})<br/>"
                       f"Original file: {escape(pr.get('file_name') or '-')}", ss["Normal"]))
    E.append(Spacer(1, 8))

    claim, conf, diff = payload["claim"], payload["confirmation"], payload["diff"] or {}

    def row(label, key, fmt=lambda x: x):
        d = diff.get(key, {})
        c = claim.get(key)
        cf = (conf or {}).get(key)
        return [label, "-" if c is None else fmt(c), "-" if cf is None else fmt(cf),
                (d.get("result") or "not compared").replace("_", " ")]

    rows = [["Field", "Worker's claim", "Other party (blind)", "Result"],
            row("Amount", "amount_paise", rupees), row("UTR", "utr"), row("Paid at", "paid_at")]
    t = Table(rows, colWidths=[90, 150, 150, 100])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
    E.append(t)
    if conf is None:
        E.append(Spacer(1, 4))
        lk = payload.get("link") or {}
        opened = lk.get("opened_at")
        E.append(Paragraph("The other party did not submit a confirmation. "
                           + (f"They opened the link at {opened}." if opened else "The link was never opened."), small))

    E.append(Spacer(1, 10))
    fr = payload["forensics"]
    E.append(Paragraph(f"Image / field risk score: {fr['risk_score']}/100 ({fr['risk_label']})", ss["Heading3"]))
    for f in fr["findings"] or [{"severity": "info", "reason": "No findings."}]:
        E.append(Paragraph(f"[{f['severity']}] {escape(f['reason'])}", ss["Normal"]))

    E.append(Spacer(1, 10))
    E.append(Paragraph("Integrity", ss["Heading3"]))
    for label, val in (("Original file SHA-256", pr["file_sha256"]), ("Previous record hash", prev_hash),
                       ("This record hash", record_hash), ("Server signature (HMAC)", signature)):
        E.append(Paragraph(f"{label}:<br/>{val}", mono))
        E.append(Spacer(1, 3))
    E.append(Spacer(1, 8))
    E.append(Paragraph("This record shows consistency between two parties' statements plus image-integrity signals. "
                       "It does not verify the payment with a bank or NPCI and is evidence support, not a legal verdict. "
                       "UPI IDs are partially masked.", small))
    doc.build(E)
    return buf.getvalue()
