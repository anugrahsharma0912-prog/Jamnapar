"""Compare the worker's claim with what the counterparty typed in blind."""
from datetime import timedelta
from ..config import TIME_TOLERANCE_MINUTES


def match(proof, conf):
    """Returns (verdict, diff). Only fields both sides provided are compared.

    amount or UTR differs        -> mismatch (these are what tamperers edit)
    only the time is off         -> partial
    everything compared agrees   -> matched
    """
    diff = {}

    def cmp(name, claimed, confirmed, equal):
        if claimed is None or confirmed is None:
            diff[name] = {"claimed": claimed, "confirmed": confirmed, "result": "not_compared"}
        else:
            diff[name] = {"claimed": claimed, "confirmed": confirmed,
                          "result": "match" if equal else "mismatch"}

    cmp("amount_paise", proof.amount_paise, conf.amount_paise,
        proof.amount_paise == conf.amount_paise)
    cmp("utr", proof.utr, conf.utr, proof.utr == conf.utr)
    close = (proof.paid_at is not None and conf.paid_at is not None and
             abs(proof.paid_at - conf.paid_at) <= timedelta(minutes=TIME_TOLERANCE_MINUTES))
    cmp("paid_at", proof.paid_at.isoformat() if proof.paid_at else None,
        conf.paid_at.isoformat() if conf.paid_at else None, close)

    if diff["amount_paise"]["result"] == "mismatch" or diff["utr"]["result"] == "mismatch":
        return "mismatch", diff
    if diff["paid_at"]["result"] == "mismatch":
        return "partial", diff
    if diff["amount_paise"]["result"] == "not_compared" and diff["utr"]["result"] == "not_compared":
        return "partial", diff
    return "matched", diff
