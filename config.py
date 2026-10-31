"""Central configuration for the pipeline validator."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Where data goes
STORAGE_DIR = BASE_DIR / "storage"
CLEAN_DIR = STORAGE_DIR / "clean"
QUARANTINE_DIR = STORAGE_DIR / "quarantine"

# Logging
LOG_DIR = BASE_DIR / "logs"
LOG_LEVEL = "INFO"

# Ingestion / retry settings
REQUEST_TIMEOUT_SECONDS = 10
RETRY_MAX_ATTEMPTS = 4          # total tries, including the first
RETRY_WAIT_MULTIPLIER = 2       # waits: 2s, 4s, 8s ...
RETRY_WAIT_MIN_SECONDS = 2
RETRY_WAIT_MAX_SECONDS = 10     # never wait longer than this

# Create folders automatically if they don't exist
for folder in (CLEAN_DIR, QUARANTINE_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)