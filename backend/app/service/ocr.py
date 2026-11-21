"""Extract payment fields from a screenshot / PDF / SMS text.

OCR is best-effort. If Tesseract is not installed the fields come back empty
and the worker types them in. Everything else still works.
"""
import io
import re
import datetime


def extract_fields(data: bytes, file_type: str) -> dict:
    text, ocr_ok = _get_text(data, file_type)
    fields = parse_text(text)
    fields["ocr_ok"] = ocr_ok
    return fields


def _get_text(data: bytes, file_type: str):
    try:
        if file_type == "txt":
            return data.decode("utf-8", errors="ignore"), True
        if file_type == "pdf":
            import fitz
            doc = fitz.open(stream=data, filetype="pdf")
            return "\n".join(p.get_text() for p in doc), True
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img), True
    except Exception:
        return "", False


def _to_paise(raw: str):
    try:
        return int(round(float(raw.replace(",", "")) * 100))
    except ValueError:
        return None


def parse_text(text: str) -> dict:
    out = {"amount_paise": None, "utr": None, "paid_at": None,
           "payer_upi": None, "payee_upi": None, "app_name": None}
    if not text:
        return out

    m = re.search(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text, re.I)
    if m:
        out["amount_paise"] = _to_paise(m.group(1))

    m = re.search(r"(?:UTR|UPI\s*Ref\w*|Transaction\s*ID|Ref(?:erence)?\.?\s*(?:No|ID)?)\D{0,15}(\d{12})\b", text, re.I)
    if not m:
        m = re.search(r"\b(\d{12})\b", text)
    if m:
        out["utr"] = m.group(1)

    ids = re.findall(r"[\w.\-]{2,}@[A-Za-z]{2,}", text)
    if ids:
        out["payer_upi"] = ids[0]
    if len(ids) > 1:
        out["payee_upi"] = ids[1]

    low = text.lower()
    for key, name in (("google pay", "gpay"), ("gpay", "gpay"), ("phonepe", "phonepe"),
                      ("paytm", "paytm"), ("bhim", "bhim"), ("amazon pay", "amazonpay")):
        if key in low:
            out["app_name"] = name
            break

    out["paid_at"] = _parse_datetime(text)
    return out


def _parse_datetime(text: str):
    day = mon = year = None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", text)
    if m:
        try:
            dt = datetime.datetime.strptime(f"{m.group(1)} {m.group(2)[:3].title()} {m.group(3)}", "%d %b %Y")
            day, mon, year = dt.day, dt.month, dt.year
        except ValueError:
            pass
    if year is None:
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
        if m:
            day, mon, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year is None:
        return None

    hour = minute = 0
    t = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?", text)
    if t:
        hour, minute = int(t.group(1)), int(t.group(2))
        ap = (t.group(3) or "").lower()
        if ap == "pm" and hour < 12:
            hour += 12
        if ap == "am" and hour == 12:
            hour = 0
    try:
        return datetime.datetime(year, mon, day, hour, minute)
    except ValueError:
        return None
