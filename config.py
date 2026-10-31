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

# Create folders automatically if they don't exist
for folder in (CLEAN_DIR, QUARANTINE_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)