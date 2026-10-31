"""Validation engine: checks records, keeps clean ones, quarantines bad ones."""
import json
import sys
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import config

# ---------- Logging setup ----------
logger.remove()  # remove default handler
logger.add(sys.stderr, level=config.LOG_LEVEL)  # print to terminal
logger.add(
    config.LOG_DIR / "pipeline.log",
    level="DEBUG",
    rotation="1 MB",     # start a new file after 1 MB
    retention="7 days",  # delete logs older than 7 days
)


# ---------- Schema ----------
class MerchantCategory(str, Enum):
    """Only these merchant categories are allowed."""
    RETAIL = "retail"
    TRAVEL = "travel"
    ENTERTAINMENT = "entertainment"
    UTILITIES = "utilities"


class TransactionRecord(BaseModel):
    """Strict schema for one financial transaction."""

    model_config = ConfigDict(extra="forbid")  # unknown fields are rejected

    transaction_id: str = Field(min_length=8)
    account_id: int = Field(strict=True)             # "123" (string) is rejected
    amount: float = Field(gt=0.0, strict=True)       # must be > 0
    currency: str = Field(pattern=r"^[A-Z]{3}$")     # exactly 3 uppercase letters
    timestamp: datetime                              # ISO string is parsed to datetime
    merchant_category: MerchantCategory
    meta_data: Optional[dict[str, Any]] = None


# ---------- Quarantine ----------
def _quarantine_record(raw_record: Any, error: ValidationError, index: int) -> None:
    """Save a failed record + its exact error text as one JSON file."""
    now = datetime.now(timezone.utc)
    filename = f"{now:%Y%m%dT%H%M%S}_record{index}_{uuid.uuid4().hex[:8]}.json"
    file_path = config.QUARANTINE_DIR / filename

    payload = {
        "quarantined_at": now.isoformat(),
        "validation_error": str(error),
        "raw_payload": raw_record,
    }
    file_path.write_text(json.dumps(payload, indent=2, default=str))
    logger.warning(f"Record {index} quarantined -> {file_path.name}")


# ---------- Main engine ----------
def validate_payload_batch(raw_records: list) -> dict:
    """Validate a batch. Returns clean records plus a summary."""
    logger.info(f"Starting validation of {len(raw_records)} records")
    clean_records: list = []
    quarantined_count = 0

    for index, raw in enumerate(raw_records):
        try:
            record = TransactionRecord.model_validate(raw)
            clean_records.append(record.model_dump(mode="json"))
            logger.debug(f"Record {index} is valid")
        except ValidationError as err:
            quarantined_count += 1
            logger.error(f"Record {index} failed validation: {err.error_count()} error(s)")
            _quarantine_record(raw, err, index)

    result = {
        "clean_records": clean_records,
        "summary": {
            "total": len(raw_records),
            "clean": len(clean_records),
            "quarantined": quarantined_count,
        },
    }
    logger.info(f"Batch complete: {result['summary']}")
    return result


# ---------- Local test ----------
if __name__ == "__main__":
    mock_records = [
        # 3 clean records
        {"transaction_id": "TXN-0001", "account_id": 1001, "amount": 49.99,
         "currency": "USD", "timestamp": "2026-10-30T10:15:00Z",
         "merchant_category": "retail", "meta_data": {"channel": "online"}},
        {"transaction_id": "TXN-0002", "account_id": 1002, "amount": 320.50,
         "currency": "EUR", "timestamp": "2026-10-30T11:20:00Z",
         "merchant_category": "travel"},
        {"transaction_id": "TXN-0003", "account_id": 1003, "amount": 15.00,
         "currency": "INR", "timestamp": "2026-10-30T12:05:00Z",
         "merchant_category": "utilities", "meta_data": None},
        # 2 corrupt records
        {"transaction_id": "TXN-0004", "account_id": 1004, "amount": -25.00,   # negative amount
         "currency": "USD", "timestamp": "2026-10-30T13:00:00Z",
         "merchant_category": "entertainment"},
        {"transaction_id": "TXN-0005", "account_id": 1005, "amount": 80.00,
         "currency": "USD", "timestamp": "2026-10-30T14:30:00Z",
         "merchant_category": "gambling"},                                     # invalid category
    ]

    output = validate_payload_batch(mock_records)

    # Save clean records for downstream use
    clean_file = config.CLEAN_DIR / "clean_records.json"
    clean_file.write_text(json.dumps(output["clean_records"], indent=2))
    logger.success(f"Clean data saved to {clean_file}")
    print("\nSUMMARY:", output["summary"])