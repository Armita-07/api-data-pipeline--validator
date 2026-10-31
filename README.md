# API Data Pipeline Validator

A lightweight Python pipeline that validates financial transaction records,
separates clean data from corrupt data, and quarantines bad records with full error details.

## Features
- Strict schema validation with Pydantic v2
- Dead Letter Queue (quarantine) for failed records, saved with payload + error text
- Structured logging with Loguru (rotation + retention)
- Centralized configuration

## Run
```bash
pip install -r requirements.txt
python validator.py
```

## Roadmap
- Ingestion handler with HTTPX + Tenacity retries
- Slack/PagerDuty alerting via webhooks