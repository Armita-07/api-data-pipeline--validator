"""Automated REST API response tests (Python + Requests)."""
import os
import threading
import time
import unittest

import pandas as pd
import requests

import config
import crosscheck
import generate_leads
import mock_hubspot
import sync_leads


class APIResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        defects = os.environ.get("MOCK_DEFECTS", "0") == "1"
        cls.server = mock_hubspot.make_server(config.HOST, 0, defects=defects)  # port 0 = free port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://{config.HOST}:{cls.server.server_address[1]}"
        cls.contacts = f"{cls.base}/crm/v3/objects/contacts"

        cls.leads = generate_leads.generate()
        cls.sync_result = sync_leads.sync(cls.base, config.DATA_DIR / "test_sync.db")
        cls.api_df = crosscheck.fetch_all_contacts(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _create(self, email, lead_id=9001):
        payload = {"properties": {"lead_id": lead_id, "email": email, "company": "QA Co"}}
        return requests.post(self.contacts, json=payload, timeout=10)

    def test_create_returns_201_with_expected_schema(self):
        resp = self._create("qa.user@example.com")
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("id", body)
        self.assertEqual(body["properties"]["email"], "qa.user@example.com")

    def test_duplicate_email_returns_409(self):
        self._create("dup@example.com")
        self.assertEqual(self._create("dup@example.com").status_code, 409)

    def test_missing_email_returns_400(self):
        resp = requests.post(self.contacts, json={"properties": {"lead_id": 1}}, timeout=10)
        self.assertEqual(resp.status_code, 400)

    def test_unknown_id_returns_404(self):
        self.assertEqual(requests.get(f"{self.contacts}/99999999", timeout=10).status_code, 404)

    def test_list_endpoint_responds_fast(self):
        start = time.perf_counter()
        resp = requests.get(self.contacts, params={"limit": 100}, timeout=10)
        self.assertEqual(resp.status_code, 200)
        self.assertLess(time.perf_counter() - start, 2.0)

    def test_every_sync_request_returned_201(self):
        self.assertEqual(self.sync_result["failed"], 0)

    def test_no_duplicate_ids_across_pages(self):
        self.assertTrue(self.api_df.hubspot_id.is_unique)

    def test_all_synced_leads_present_in_api(self):
        missing = set(self.leads.email) - set(self.api_df.email)
        self.assertEqual(len(missing), 0, f"{len(missing)} leads accepted but missing from API")

    def test_field_values_match_source(self):
        merged = self.leads.merge(self.api_df, on="email", suffixes=("_src", "_api"))
        bad_company = merged[merged.company_src != merged.company_api.fillna("")]
        bad_phone = merged[merged.phone_src != merged.phone_api.fillna("")]
        self.assertEqual(len(bad_company), 0, f"{len(bad_company)} company mismatches")
        self.assertEqual(len(bad_phone), 0, f"{len(bad_phone)} phone mismatches")


if __name__ == "__main__":
    unittest.main()