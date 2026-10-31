"""Orchestrator: Fetch -> Validate -> Save clean -> Quarantine bad -> Alert."""
import json
import threading
from datetime import datetime, timezone
from http.server import HTTPServer

import httpx
from loguru import logger

import config
from alerting import send_batch_alert, send_failure_alert
from ingestion import MockAPIHandler, fetch_api_data
from validator import validate_payload_batch


def run_full_pipeline(endpoint_url: str, headers: dict = None) -> dict:
    """Run the complete end-to-end workflow and return the validation result."""
    logger.info("========== PIPELINE START ==========")

    # 1. FETCH (with retries)
    try:
        raw_records = fetch_api_data(endpoint_url, headers)
    except httpx.HTTPError as exc:
        send_failure_alert(exc)
        raise  # stop the pipeline

    # 2. VALIDATE (bad rows are quarantined inside this call)
    result = validate_payload_batch(raw_records)

    # 3. SAVE clean data (one timestamped file per run)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    clean_file = config.CLEAN_DIR / f"clean_records_{stamp}.json"
    clean_file.write_text(json.dumps(result["clean_records"], indent=2))
    logger.success(f"{len(result['clean_records'])} clean records saved -> {clean_file.name}")

    # 4. ALERT if anything was quarantined
    send_batch_alert(result["summary"], result["error_details"])

    logger.info(f"========== PIPELINE END: {result['summary']} ==========")
    return result


if __name__ == "__main__":
    # Start the local mock API (replace base_url with a real API in production)
    server = HTTPServer(("127.0.0.1", 0), MockAPIHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    run_full_pipeline(f"{base_url}/transactions")

    server.shutdown()