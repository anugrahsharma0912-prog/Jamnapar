"""Tamper signals. Each check returns findings: {check, severity, reason, region?}.

These are risk signals, not proof. A clean score does NOT prove authenticity;
the two-party confirmation is the real check.
"""
import io
import re
import datetime

EDITORS = ("photoshop", "gimp", "canva", "snapseed", "picsart", "pixlr", "lightroom",
           "affinity", "figma", "photopea", "paint.net", "inkscape", "illustrator",
           "coreldraw", "faceapp", "meitu")
WEIGHTS = {"high": 40, "medium": 20, "low": 8, "info": 0}


def finding(check, severity, reason, region=None):
    f = {"check": check, "severity": severity, "reason": reason}
    if region:
        f["region"] = region
    return f


def score(findings) -> int:
    return min(100, sum(WEIGHTS.get(f["severity"], 0) for f in findings))


def risk_label(s: int) -> str:
    return "low" if s < 20 else "medium" if s < 50 else "high"


# ---------- file-level checks (run once at upload) ----------

def analyze_file(data: bytes, file_type: str) -> list:
    findings = []
    try:
        if file_type == "pdf":
            _pdf_metadata(data, findings)
        elif file_type == "txt":
            findings.append(finding("text", "info",
                "Plain text has no image-integrity signals; rely on the other party's confirmation."))
        else:
            _image_checks(data, file_type, findings)
    except Exception as e:  # never let analysis crash an upload
        findings.append(finding("analysis", "info", f"Could not fully analyze file: {type(e).__name__}"))
    return findings


def _pdf_metadata(data, findings):
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    meta = doc.metadata or {}
    blob = f"{meta.get('producer','')} {meta.get('creator','')}".lower()
    hit = next((e for e in EDITORS if e in blob), None)
    if hit:
        findings.append(finding("metadata", "high", f"PDF was produced by an editing tool ({hit})."))
    c, m = meta.get("creationDate"), meta.get("modDate")
    if c and m and c != m:
        findings.append(finding("metadata", "medium", "PDF modified date differs from created date."))


def _image_checks(data, file_type, findings):
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.load()

    # metadata: software tags in EXIF / PNG text chunks
    parts = [str(v) for v in img.info.values() if isinstance(v, (str, bytes))]
    try:
        exif = img.getexif()
        if exif:
            parts.append(str(exif.get(305, "")))  # 305 = Software tag
    except Exception:
        pass
    blob = " ".join(parts).lower()
    hit = next((e for e in EDITORS if e in blob), None)
    if hit:
        findings.append(finding("metadata", "high", f"Image metadata names an editing tool ({hit})."))

    # Error Level Analysis only means something on JPEGs
    if (img.format or "").upper() == "JPEG":
        _ela(img, findings)
    else:
        findings.append(finding("ela", "info",
            "Pixel-compression analysis is not reliable on PNG/WebP screenshots; metadata and field checks were used."))


def _ela(img, findings, quality=90, block=32):
    import numpy as np
    from PIL import Image
    orig = img.convert("RGB")
    buf = io.BytesIO()
    orig.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    comp = Image.open(buf).convert("RGB")
    diff = np.abs(np.asarray(orig, dtype=np.int16) - np.asarray(comp, dtype=np.int16)).sum(axis=2)
    h, w = diff.shape
    h2, w2 = (h // block) * block, (w // block) * block
    if h2 == 0 or w2 == 0:
        return
    blocks = diff[:h2, :w2].reshape(h2 // block, block, w2 // block, block).mean(axis=(1, 3))
    med = float(np.median(blocks))
    mx = float(blocks.max())
    hot = float((blocks > max(3.5 * med, 10)).mean())
    if mx > 10 and mx > 3.5 * max(med, 1.0) and hot < 0.05:
        r, c = np.unravel_index(int(blocks.argmax()), blocks.shape)
        findings.append(finding("ela", "medium",
            "A small region compresses very differently from the rest of the image (possible local edit).",
            region={"x": int(c * block), "y": int(r * block), "w": block, "h": block}))


# ---------- field-level checks (re-run whenever fields change) ----------

def check_fields(proof) -> list:
    f = []
    if not proof.utr:
        f.append(finding("format", "low", "UTR / transaction ID is missing."))
    elif not re.fullmatch(r"\d{12}", proof.utr):
        f.append(finding("format", "medium", "UTR is not 12 digits, which is the usual UPI format."))
    if proof.amount_paise is None:
        f.append(finding("format", "low", "Amount is missing."))
    elif proof.amount_paise <= 0:
        f.append(finding("format", "medium", "Amount is zero or negative."))
    elif proof.amount_paise > 10_000_000:
        f.append(finding("format", "medium", "Amount exceeds the usual 1,00,000 per-transaction UPI limit."))
    if proof.paid_at:
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if proof.paid_at > now + datetime.timedelta(days=1):
            f.append(finding("format", "high", "Payment time is in the future."))
    return f
