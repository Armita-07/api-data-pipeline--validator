"""Cross-verify database state (SQLite) against API output (SQL + Pandas), write a bug report."""
import sqlite3
import sys
from contextlib import closing
from datetime import datetime

import pandas as pd
import requests

import config

COUNT_SQL = """
SELECT (SELECT COUNT(*) FROM synced_leads WHERE http_status = 201) AS db_synced,
       (SELECT COUNT(*) FROM api_snapshot)                         AS api_total
"""

# Leads the API accepted (201) but cannot return
MISSING_SQL = """
SELECT s.lead_id, s.email, s.hubspot_id
FROM synced_leads s
LEFT JOIN api_snapshot a ON a.email = s.email
WHERE s.http_status = 201 AND a.email IS NULL
ORDER BY s.lead_id
"""

# Leads whose stored values differ from what we sent
MISMATCH_SQL = """
SELECT s.lead_id, s.email, s.hubspot_id,
       s.company AS expected_company, a.company AS api_company,
       s.phone   AS expected_phone,   a.phone   AS api_phone
FROM synced_leads s
JOIN api_snapshot a ON a.email = s.email
WHERE s.company <> COALESCE(a.company, '') OR s.phone <> COALESCE(a.phone, '')
ORDER BY s.lead_id
"""


def fetch_all_contacts(base_url: str = config.BASE_URL) -> pd.DataFrame:
    """Read every contact from the API, following pagination."""
    url = f"{base_url}/crm/v3/objects/contacts"
    contacts, after = [], None
    with requests.Session() as session:
        while True:
            params = {"limit": config.PAGE_SIZE}
            if after:
                params["after"] = after
            resp = session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            contacts += [{"hubspot_id": c["id"], **c["properties"]} for c in data["results"]]
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
    return pd.DataFrame(contacts, columns=["hubspot_id", "lead_id", "email", "company", "phone"])


def write_report(counts, missing, mismatch, base_url):
    c = counts.iloc[0]
    company_bad = mismatch[mismatch.expected_company != mismatch.api_company.fillna("")]
    phone_bad = mismatch[mismatch.expected_phone != mismatch.api_phone.fillna("")]

    lines = [
        "# Data Integrity Report",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M}_",
        "",
        "## Summary",
        f"- Leads accepted by API (HTTP 201): {c.db_synced}",
        f"- Contacts returned by API: {c.api_total}",
        f"- Accepted but missing: {len(missing)}",
        f"- Company value mismatches: {len(company_bad)}",
        f"- Phone value mismatches: {len(phone_bad)}",
    ]

    if len(missing):
        ex = missing.iloc[0]
        ids = ", ".join(str(i) for i in missing.lead_id.head(10))
        lines += [
            "", "## BUG-001: Contact accepted (201) but never stored",
            f"- Affected leads: {len(missing)} (lead_ids: {ids})",
            "- Reproduction:",
            f"  1. Sync lead {ex.lead_id} ({ex.email}). The API replies 201 with id `{ex.hubspot_id}`.",
            f"  2. Request `GET {base_url}/crm/v3/objects/contacts/{ex.hubspot_id}`.",
            "  3. Expected: 200 with the contact. Actual: 404.",
        ]
    if len(company_bad):
        ex = company_bad.iloc[0]
        lines += [
            "", "## BUG-002: Long company names are truncated",
            f"- Affected leads: {len(company_bad)}",
            "- Reproduction:",
            f"  1. Create a contact with company `{ex.expected_company}`.",
            f"  2. Read it back with `GET {base_url}/crm/v3/objects/contacts/{ex.hubspot_id}`.",
            f"  3. Expected the full name. Actual: `{ex.api_company}` (cut at 30 characters).",
        ]
    if len(phone_bad):
        ex = phone_bad.iloc[0]
        lines += [
            "", "## BUG-003: Phone numbers with an extension are wiped",
            f"- Affected leads: {len(phone_bad)}",
            "- Reproduction:",
            f"  1. Create a contact with phone `{ex.expected_phone}`.",
            f"  2. Read it back with `GET {base_url}/crm/v3/objects/contacts/{ex.hubspot_id}`.",
            "  3. Expected the phone number. Actual: empty string.",
        ]

    path = config.REPORT_DIR / "data_integrity_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(base_url: str = config.BASE_URL, db_path=config.DB_PATH) -> dict:
    api_df = fetch_all_contacts(base_url)
    with closing(sqlite3.connect(db_path)) as conn:
        api_df.to_sql("api_snapshot", conn, if_exists="replace", index=False)
        counts = pd.read_sql(COUNT_SQL, conn)
        missing = pd.read_sql(MISSING_SQL, conn)
        mismatch = pd.read_sql(MISMATCH_SQL, conn)
    report = write_report(counts, missing, mismatch, base_url)
    return {"counts": counts, "missing": missing, "mismatch": mismatch, "report": report}


if __name__ == "__main__":
    result = run()
    issues = len(result["missing"]) + len(result["mismatch"])
    print(result["counts"].to_string(index=False))
    print(f"Missing: {len(result['missing'])} | Mismatched: {len(result['mismatch'])}")
    print(f"Report written to {result['report']}")
    sys.exit(1 if issues else 0)