"""Central settings."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
LEADS_CSV = DATA_DIR / "leads_sheet.csv"
DB_PATH = DATA_DIR / "sync_state.db"

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"

LEAD_COUNT = 520      # "500+" leads
PAGE_SIZE = 100

for folder in (DATA_DIR, REPORT_DIR):
    folder.mkdir(exist_ok=True)