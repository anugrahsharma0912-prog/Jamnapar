"""Builds the live risk report: stored file findings + field checks + reuse checks."""
from . import forensics
from .hashing import hamming_hex
from ..models import Proof


def reuse_findings(proof, db) -> list:
    out = []
    for o in db.query(Proof).filter(Proof.id != proof.id).all():
        same_worker = (o.worker_phone or "") == (proof.worker_phone or "")
        if proof.utr and o.utr == proof.utr:
            if same_worker:
                out.append(forensics.finding("reuse", "low", "This UTR was already uploaded by the same worker."))
            else:
                out.append(forensics.finding("reuse", "high",
                    "The same UTR was already claimed by a different worker. Two people cannot both be paid by one transaction."))
        elif o.file_sha256 == proof.file_sha256:
            out.append(forensics.finding("reuse", "medium", "This exact file was already uploaded under another proof."))
        elif proof.phash and o.phash and hamming_hex(proof.phash, o.phash) <= 3:
            out.append(forensics.finding("reuse", "medium", "This image looks nearly identical to another uploaded proof."))
    return out


def build_report(proof, db) -> dict:
    findings = list(proof.file_findings or [])
    findings += forensics.check_fields(proof)
    findings += reuse_findings(proof, db)
    s = forensics.score(findings)
    return {"risk_score": s, "risk_label": forensics.risk_label(s), "findings": findings}
