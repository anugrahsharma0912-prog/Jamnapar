import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../backend
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")
RECORD_DIR = os.path.join(STORAGE_DIR, "records")

# Used to sign record timestamps. Set JAMNAPAR_SECRET in your environment for real use.
SECRET = os.environ.get("JAMNAPAR_SECRET", "dev-secret-change-me")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
LINK_TTL_DAYS = 7
TIME_TOLERANCE_MINUTES = 5

for _d in (UPLOAD_DIR, RECORD_DIR):
    os.makedirs(_d, exist_ok=True)
    