"""Ingestion engine: fetches data from a REST API with retries, then validates it."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import httpx
from loguru import logger
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

import config
from validator import validate_payload_batch


# ---------- Retry rules ----------
def _is_retryable(exc: BaseException) -> bool:
    """Retry only on timeouts, 429 (rate limit), and 5xx (server errors)."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    return False  # e.g. 404 or 401 will not get better by retrying


def _log_retry(retry_state: RetryCallState) -> None:
    """Runs before each wait, so the logs show every retry."""
    error = retry_state.outcome.exception()
    wait_seconds = retry_state.next_action.sleep
    logger.warning(
        f"Attempt {retry_state.attempt_number}/{config.RETRY_MAX_ATTEMPTS} failed "
        f"({error!r}). Retrying in {wait_seconds:.0f}s..."
    )


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(
        multiplier=config.RETRY_WAIT_MULTIPLIER,
        min=config.RETRY_WAIT_MIN_SECONDS,
        max=config.RETRY_WAIT_MAX_SECONDS,
    ),
    stop=stop_after_attempt(config.RETRY_MAX_ATTEMPTS),
    before_sleep=_log_retry,
    reraise=True,  # after the last attempt, raise the real error (not a tenacity wrapper)
)
def _get_with_retry(endpoint_url: str, headers: Optional[dict]):
    """One HTTP GET. Tenacity re-runs this function when it raises a retryable error."""
    with httpx.Client(timeout=config.REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(endpoint_url, headers=headers)
        response.raise_for_status()  # turns 4xx/5xx into an HTTPStatusError
        return response.json()


# ---------- Public functions ----------
def fetch_api_data(endpoint_url: str, headers: dict = None) -> list:
    """Fetch records from an API. Retries on failure; raises if all attempts fail."""
    logger.info(f"Fetching data from {endpoint_url}")
    try:
        data = _get_with_retry(endpoint_url, headers)
    except httpx.HTTPError as exc:
        logger.critical(f"INGESTION FAILED after all attempts: {exc!r}. Stopping pipeline.")
        raise

    # Accept either a plain list or {"records": [...]}
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of records, got {type(data).__name__}")

    logger.success(f"Fetched {len(data)} records")
    return data


def run_pipeline(endpoint_url: str, headers: dict = None) -> dict:
    """Full flow: fetch from API -> validate -> return clean records + summary."""
    raw_records = fetch_api_data(endpoint_url, headers)
    return validate_payload_batch(raw_records)


# ---------- Local test with a mock API server ----------
MOCK_RECORDS = [
    {"transaction_id": "TXN-1001", "account_id": 2001, "amount": 59.99, "currency": "USD",
     "timestamp": "2026-10-31T09:00:00Z", "merchant_category": "retail"},
    {"transaction_id": "TXN-1002", "account_id": 2002, "amount": 410.00, "currency": "EUR",
     "timestamp": "2026-10-31T09:30:00Z", "merchant_category": "travel",
     "meta_data": {"channel": "mobile"}},
    {"transaction_id": "TXN-1003", "account_id": 2003, "amount": 22.50, "currency": "INR",
     "timestamp": "2026-10-31T10:00:00Z", "merchant_category": "utilities"},
    {"transaction_id": "TXN-1004", "account_id": 2004, "amount": -5.00, "currency": "USD",
     "timestamp": "2026-10-31T10:15:00Z", "merchant_category": "entertainment"},  # bad amount
    {"transaction_id": "TXN-1005", "account_id": 2005, "amount": 75.00, "currency": "usd",
     "timestamp": "2026-10-31T10:45:00Z", "merchant_category": "retail"},         # lowercase currency
]


class MockAPIHandler(BaseHTTPRequestHandler):
    """A tiny fake API running on your own computer."""
    flaky_calls = 0

    def do_GET(self):
        if self.path == "/transactions":        # always works
            self._send(200, MOCK_RECORDS)
        elif self.path == "/flaky":             # fails twice with 503, then works
            MockAPIHandler.flaky_calls += 1
            if MockAPIHandler.flaky_calls <= 2:
                self._send(503, {"error": "Service Unavailable"})
            else:
                self._send(200, MOCK_RECORDS)
        elif self.path == "/down":              # always fails
            self._send(500, {"error": "Internal Server Error"})
        else:
            self._send(404, {"error": "Not Found"})

    def _send(self, status: int, body) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence the server's own console output
        pass


if __name__ == "__main__":
    RUN_FAILURE_DEMO = False  # set True to see the critical alert (takes ~14 seconds)

    server = HTTPServer(("127.0.0.1", 0), MockAPIHandler)  # port 0 = pick any free port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    logger.info("=== DEMO 1: healthy API ===")
    result = run_pipeline(f"{base_url}/transactions")
    print("SUMMARY:", result["summary"], "\n")

    logger.info("=== DEMO 2: flaky API (2 failures, then success) ===")
    result = run_pipeline(f"{base_url}/flaky")
    print("SUMMARY:", result["summary"], "\n")

    if RUN_FAILURE_DEMO:
        logger.info("=== DEMO 3: API that never recovers ===")
        try:
            run_pipeline(f"{base_url}/down")
        except httpx.HTTPError:
            logger.info("Pipeline stopped as expected.")

    server.shutdown()