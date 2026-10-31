"""Alerting module: sends a batch summary to Slack via webhook (or logs it locally)."""
import os
from collections import Counter

import httpx
from loguru import logger

import config


def build_alert_text(summary: dict, error_details: list) -> str:
    """Turn the batch results into a readable message."""
    total = summary["total"]
    quarantined = summary["quarantined"]
    error_rate = (quarantined / total * 100) if total else 0.0

    # Count how often each (field, message) error happened
    counts = Counter((e["field"], e["message"]) for e in error_details)
    top_errors = "\n".join(
        f"• {field}: {message} ({n}x)"
        for (field, message), n in counts.most_common(3)
    )

    text = (
        ":rotating_light: *Data Pipeline Alert*\n"
        f"Total: {total} | Clean: {summary['clean']} | "
        f"Quarantined: {quarantined} | Error rate: {error_rate:.1f}%\n"
        f"*Top validation errors:*\n{top_errors}"
    )
    return text[:1500]  # keep the message a sensible size


def _deliver(text: str) -> bool:
    """POST to the webhook, or log locally if no URL is configured."""
    webhook_url = os.environ.get(config.ALERT_WEBHOOK_ENV_VAR)

    if not webhook_url:
        logger.warning(
            f"{config.ALERT_WEBHOOK_ENV_VAR} is not set. "
            f"Alert logged locally instead:\n{text}"
        )
        return False

    try:
        response = httpx.post(
            webhook_url, json={"text": text}, timeout=config.ALERT_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        logger.success("Alert sent to webhook")
        return True
    except httpx.HTTPError as exc:
        # A broken alert must never crash the pipeline
        logger.error(f"Failed to send alert: {exc!r}")
        return False


def send_batch_alert(summary: dict, error_details: list) -> bool:
    """Send an alert only if the quarantined count passes the threshold."""
    if summary["quarantined"] <= config.ALERT_MIN_QUARANTINED:
        logger.info("No quarantined records. No alert needed.")
        return False
    return _deliver(build_alert_text(summary, error_details))


def send_failure_alert(error: Exception) -> bool:
    """Alert when the whole pipeline stops (for example, the API is down)."""
    return _deliver(f":fire: *Pipeline STOPPED*\nReason: {error!r}")