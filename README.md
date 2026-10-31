# API and Data Pipeline Validator

Automated checks that validate REST API responses for 500+ lead records synced from a
Google Sheets-style export to a HubSpot-style API. The project then cross-verifies the
database state against the API output with SQL and documents any data integrity bugs
with reproduction steps.

**Stack:** Python, Requests, Pandas, SQL (SQLite), Postman

> **Demo project.** The lead data is synthetic, the "Google Sheet" is a generated CSV,
> and the "HubSpot" API is a local mock that copies HubSpot's contacts endpoint shape.
> The mock contains three deliberately planted defects so the checks have real bugs to find.

---

## Table of contents

1. [The problem this solves](#the-problem-this-solves)
2. [How it works](#how-it-works)
3. [Project structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Setup](#setup)
6. [Run the pipeline](#run-the-pipeline)
7. [Run the tests](#run-the-tests)
8. [Run the Postman collection](#run-the-postman-collection)
9. [The three planted bugs](#the-three-planted-bugs)
10. [File-by-file reference](#file-by-file-reference)
11. [Configuration](#configuration)
12. [Command cheat sheet](#command-cheat-sheet)
13. [Troubleshooting](#troubleshooting)
14. [Limitations and next steps](#limitations-and-next-steps)

---

## The problem this solves

When a sync copies leads from a spreadsheet into a CRM through an API, the API can answer
**HTTP 201 (success)** and still lose or corrupt data. This project does not trust the
success status. It records what was **sent**, reads back what the API **actually holds**,
and compares the two with SQL.

Result on the included data: the API accepts all 520 leads, but only 515 can be read
back, and 21 contacts hold altered values.

## How it works

```
generate_leads.py -> data/leads_sheet.csv     (520 leads, the "Google Sheet")
        |
        v
sync_leads.py --- POST each lead (Requests) ---> mock_hubspot.py (the "HubSpot" API)
        |                                                |
        v                                                |
SQLite table: synced_leads                               |
("what we sent")                                         |
        |                                                v
        |             crosscheck.py --- GET every page ---+
        |                   |
        |                   v
        |           SQLite table: api_snapshot ("what the API holds")
        v                   v
        +---- SQL joins compare both ----> reports/data_integrity_report.md
```

1. `generate_leads.py` creates 520 fake leads and saves them as a CSV.
2. `sync_leads.py` posts each lead to the API with Requests and logs every response in SQLite.
3. `crosscheck.py` reads all contacts back (following pagination) into Pandas, loads them
   into SQLite, and runs SQL joins against the sync log.
4. Differences are written to `reports/data_integrity_report.md` with reproduction steps.
5. `tests/` (Python) and `postman/` (Postman) contain automated API response checks.

## Project structure

```
api-data-pipeline-validator/
├── README.md
├── requirements.txt
├── .gitignore
├── config.py                  # paths, host/port, lead count, page size
├── generate_leads.py          # builds the fake "Google Sheet" CSV
├── mock_hubspot.py            # local HubSpot-style API with planted bugs
├── sync_leads.py              # CSV -> API via Requests, logs state in SQLite
├── crosscheck.py              # Pandas + SQL: database vs API, writes the report
├── tests/
│   ├── __init__.py            # empty file, makes tests a package
│   └── test_api_responses.py  # 9 automated API tests (unittest + Requests)
├── postman/
│   └── lead_api.postman_collection.json
├── reports/                   # generated: data_integrity_report.md
└── data/                      # generated (git-ignored): CSV and SQLite files
```

## Prerequisites

- Python 3.9 or newer (`python --version` to check)
- Git
- Postman (optional, only for the Postman collection)
- VS Code (optional)

## Setup

### Windows (PowerShell)

```powershell
git clone https://github.com/YOUR_USERNAME/api-data-pipeline-validator.git
cd api-data-pipeline-validator
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### macOS / Linux

```bash
git clone https://github.com/YOUR_USERNAME/api-data-pipeline-validator.git
cd api-data-pipeline-validator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The prompt should show `(venv)` once the environment is active.

## Run the pipeline

You need **two terminals**, both inside the project folder with the venv activated.

### Terminal 1: start the mock API (leave it running)

```bash
python mock_hubspot.py
```

Expected output, and the prompt does not return:

```
Mock HubSpot API running at http://127.0.0.1:8765 (with planted defects). Ctrl+C to stop.
```

To run a healthy API with no bugs instead:

```bash
python mock_hubspot.py --no-defects
```

### Terminal 2: generate, sync, cross-check

```bash
python generate_leads.py
python sync_leads.py
python crosscheck.py
```

Expected output:

```
Wrote 520 leads -> .../data/leads_sheet.csv
Synced 520 leads, 0 failed
 db_synced  api_total
       520        515
Missing: 5 | Mismatched: 21
Report written to .../reports/data_integrity_report.md
```

Then open `reports/data_integrity_report.md` to read the documented bugs.

`crosscheck.py` exits with code **1** when it finds any issue and **0** when the data
matches, so it can be used as a pass/fail step in CI.

**Important:** the mock API keeps contacts in memory. Before running `sync_leads.py` a
second time, stop Terminal 1 with `Ctrl + C` and start `python mock_hubspot.py` again.
Otherwise every lead is rejected as a duplicate (HTTP 409).

## Run the tests

The tests start their **own** mock server on a random free port, so Terminal 1 is not needed.

### 1. All tests against a healthy API (expect all green)

```bash
python -m unittest discover -s tests -t . -v
```

Expected ending:

```
Ran 9 tests in ~4s

OK
```

### 2. All tests against the buggy API (expect 2 failures)

Windows (PowerShell):

```powershell
$env:MOCK_DEFECTS="1"
python -m unittest discover -s tests -t . -v
Remove-Item Env:MOCK_DEFECTS
```

macOS / Linux:

```bash
MOCK_DEFECTS=1 python -m unittest discover -s tests -t . -v
```

Expected failures:

- `test_all_synced_leads_present_in_api` (5 leads accepted but missing)
- `test_field_values_match_source` (company and phone mismatches)

Expected ending: `FAILED (failures=2)`. This proves the tests can detect real bugs.

### 3. Run one test file directly

```bash
python -m unittest tests.test_api_responses -v
```

### 4. Run a single test

```bash
python -m unittest tests.test_api_responses.APIResponseTests.test_duplicate_email_returns_409 -v
```

### What the 9 tests check

| Test | Checks |
|---|---|
| `test_create_returns_201_with_expected_schema` | Create returns 201, an `id`, and the right email |
| `test_duplicate_email_returns_409` | Same email twice gives 409 |
| `test_missing_email_returns_400` | Missing email gives 400 |
| `test_unknown_id_returns_404` | Unknown contact id gives 404 |
| `test_list_endpoint_responds_fast` | List endpoint returns 200 in under 2 seconds |
| `test_every_sync_request_returned_201` | All 520 sync requests succeeded |
| `test_no_duplicate_ids_across_pages` | Pagination never repeats a contact |
| `test_all_synced_leads_present_in_api` | Every lead sent can be read back |
| `test_field_values_match_source` | Company and phone match the source data |

## Run the Postman collection

1. Start the mock API: `python mock_hubspot.py`
2. Open Postman, click **Import**, and select `postman/lead_api.postman_collection.json`.
3. Right-click the collection, choose **Run collection**, and click **Run**.
4. All 4 requests should pass:
   - Create contact (201, has `id` and email)
   - List contacts (200, at most 100 results, under 2000 ms)
   - Get contact by id (200, id matches the one just created)
   - Get unknown contact (404 with an error body)

The collection variable `baseUrl` defaults to `http://127.0.0.1:8765`. The create request
saves the new contact's id into the `contactId` variable, which the next request uses.

Optional, from a terminal with Node.js installed:

```bash
npx newman run postman/lead_api.postman_collection.json
```

## The three planted bugs

The mock API (when run without `--no-defects`) contains these defects, and the
cross-check finds all three.

| Bug | What the API does | Affected leads | How it is found |
|---|---|---|---|
| **BUG-001** | Replies 201 but never stores every 97th lead | 5 (ids 97, 194, 291, 388, 485) | SQL LEFT JOIN anti-join: sent but not returned |
| **BUG-002** | Cuts company names longer than 30 characters | 13 (every 40th lead) | SQL JOIN: company differs from source |
| **BUG-003** | Wipes phone numbers that contain an extension (`x`) | 10 (every 50th lead) | SQL JOIN: phone differs from source |

Leads 200 and 400 trigger both BUG-002 and BUG-003, so the report shows
13 + 10 - 2 = **21** mismatched contacts.

## File-by-file reference

| File | Role |
|---|---|
| `config.py` | Central settings. Creates the `data/` and `reports/` folders. |
| `generate_leads.py` | Generates 520 leads with a fixed random seed so every run is identical. |
| `mock_hubspot.py` | Local HTTP server with `POST /crm/v3/objects/contacts`, `GET /crm/v3/objects/contacts` (cursor pagination), and `GET /crm/v3/objects/contacts/{id}`. |
| `sync_leads.py` | Sends each lead with a Requests session and stores the result in the SQLite table `synced_leads`. |
| `crosscheck.py` | Fetches all contacts into Pandas, loads them as `api_snapshot`, runs three SQL queries (counts, missing, mismatched), and writes the Markdown report. |
| `tests/test_api_responses.py` | Nine unittest tests that run against a self-started mock server. |
| `postman/lead_api.postman_collection.json` | Four Postman requests with test scripts. |

### The SQL queries in `crosscheck.py`

```sql
-- Counts
SELECT (SELECT COUNT(*) FROM synced_leads WHERE http_status = 201) AS db_synced,
       (SELECT COUNT(*) FROM api_snapshot)                         AS api_total;

-- Accepted by the API but missing (anti-join)
SELECT s.lead_id, s.email, s.hubspot_id
FROM synced_leads s
LEFT JOIN api_snapshot a ON a.email = s.email
WHERE s.http_status = 201 AND a.email IS NULL;

-- Stored with different values
SELECT s.lead_id, s.email, s.company AS expected_company, a.company AS api_company,
       s.phone AS expected_phone, a.phone AS api_phone
FROM synced_leads s
JOIN api_snapshot a ON a.email = s.email
WHERE s.company <> COALESCE(a.company, '') OR s.phone <> COALESCE(a.phone, '');
```

## Configuration

All settings live in `config.py`.

| Setting | Default | Meaning |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `8765` | Where the mock API listens |
| `LEAD_COUNT` | `520` | Number of generated leads |
| `PAGE_SIZE` | `100` | Contacts requested per API page |
| `LEADS_CSV` | `data/leads_sheet.csv` | The generated "sheet" |
| `DB_PATH` | `data/sync_state.db` | SQLite file for sync state |

Environment variable: `MOCK_DEFECTS=1` turns the planted bugs on during tests (off by default).

## Command cheat sheet

| Goal | Command |
|---|---|
| Create environment | `python -m venv venv` |
| Activate (Windows) | `venv\Scripts\activate` |
| Activate (macOS/Linux) | `source venv/bin/activate` |
| Install libraries | `pip install -r requirements.txt` |
| Start buggy mock API | `python mock_hubspot.py` |
| Start healthy mock API | `python mock_hubspot.py --no-defects` |
| Generate leads | `python generate_leads.py` |
| Sync leads | `python sync_leads.py` |
| Cross-check and report | `python crosscheck.py` |
| Run all tests (healthy) | `python -m unittest discover -s tests -t . -v` |
| Run all tests (buggy, PowerShell) | `$env:MOCK_DEFECTS="1"` then the test command |
| Run all tests (buggy, macOS/Linux) | `MOCK_DEFECTS=1 python -m unittest discover -s tests -t . -v` |
| Clear the variable (PowerShell) | `Remove-Item Env:MOCK_DEFECTS` |
| Run one test file | `python -m unittest tests.test_api_responses -v` |
| Stop the mock API | `Ctrl + C` in its terminal |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| A script runs and exits with no output | The file is unsaved or missing its last lines. Press `Ctrl + S` and check that the file ends with its `if __name__ == "__main__":` block. |
| `no such table: synced_leads` | `sync_leads.py` has not run successfully. Run it before `crosscheck.py`. |
| `Ran 0 tests` or `No module named 'tests.test_api_responses'` | Check `dir tests`. It needs `__init__.py` and `test_api_responses.py` with a single `.py`. A name like `test_api_responses.py.py` is a common mistake. |
| Sync shows many failures or `409` | The mock API still holds earlier contacts. Restart it with `Ctrl + C`, then `python mock_hubspot.py`. |
| `ConnectionError` or connection refused | The mock API is not running. Start it in Terminal 1 first. |
| `Address already in use` | Another copy is running on port 8765. Stop it, or change `PORT` in `config.py`. |
| `ModuleNotFoundError: requests` or `pandas` | The venv is not active or the install was skipped. Activate it and run `pip install -r requirements.txt`. |
| `code .` is not recognized | Open VS Code manually and use File, then Open Folder. |

## Limitations and next steps

- The API is a mock, not real HubSpot, and the data is synthetic.
- No authentication, retries, or rate-limit handling (a real integration needs a bearer token and retry logic for 429 and 5xx).
- Only create and read are tested. Update and delete are not covered.
- Contacts are matched by email. A sync that changed the email itself would not be matched.
- Everything is held in memory, which is fine for 520 records but not for millions.

Possible next steps: read leads from the real Google Sheets API, point the checks at a free
HubSpot developer account, add retry logic with backoff, add tests for update and delete,
run the tests in GitHub Actions, and send failures to Slack.