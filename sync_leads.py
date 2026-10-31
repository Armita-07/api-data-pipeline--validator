"""Sync leads from the 'sheet' (CSV) to the API using Requests; track state in SQLite."""
import sqlite3
from contextlib import closing

import pandas as pd
import requests

import config


def sync(base_url: str = config.BASE_URL, db_path=config.DB_PATH) -> dict:
    leads = pd.read_csv(config.LEADS_CSV, dtype={"phone": str})
    url = f"{base_url}/crm/v3/objects/contacts"
    ok = failed = 0

    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("DROP TABLE IF EXISTS synced_leads")
        conn.execute(
            """CREATE TABLE synced_leads (
                   lead_id INTEGER PRIMARY KEY, email TEXT, company TEXT,
                   phone TEXT, hubspot_id TEXT, http_status INTEGER)"""
        )
        with requests.Session() as session:
            for row in leads.itertuples(index=False):
                payload = {"properties": {
                    "lead_id": int(row.lead_id), "email": row.email,
                    "firstname": row.first_name, "lastname": row.last_name,
                    "company": row.company, "phone": row.phone,
                }}
                resp = session.post(url, json=payload, timeout=10)
                hubspot_id = resp.json().get("id") if resp.status_code == 201 else None
                conn.execute(
                    "INSERT INTO synced_leads VALUES (?, ?, ?, ?, ?, ?)",
                    (int(row.lead_id), row.email, row.company, row.phone,
                     hubspot_id, resp.status_code),
                )
                if resp.status_code == 201:
                    ok += 1
                else:
                    failed += 1
        conn.commit()

    print(f"Synced {ok} leads, {failed} failed")
    return {"ok": ok, "failed": failed}


if __name__ == "__main__":
    sync()