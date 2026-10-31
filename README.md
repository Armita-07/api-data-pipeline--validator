# API Data Pipeline Validator

A lightweight Python pipeline that validates financial transaction records,
separates clean data from corrupt data, and quarantines bad records with full error details.

## Features
- Strict schema validation with Pydantic v2
- Dead Letter Queue: failed records saved with payload + exact error text
- HTTPX ingestion with Tenacity retries (timeouts, 429, 5xx) and exponential backoff
- Slack webhook alerts with error-rate summary (URL read from environment variable)
- Loguru structured logging with rotation

## Run
    pip install -r requirements.txt
    python pipeline.py

## Roadmap
- Ingestion handler with HTTPX + Tenacity retries
- Slack/PagerDuty alerting via webhooks

Optional: `$env:NOTIFICATION_WEBHOOK_URL="<slack-webhook-url>"` to enable alerts.