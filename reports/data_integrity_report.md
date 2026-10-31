# Data Integrity Report
_Generated 2026-10-31 18:47_

## Summary
- Leads accepted by API (HTTP 201): 520
- Contacts returned by API: 515
- Accepted but missing: 5
- Company value mismatches: 13
- Phone value mismatches: 10

## BUG-001: Contact accepted (201) but never stored
- Affected leads: 5 (lead_ids: 97, 194, 291, 388, 485)
- Reproduction:
  1. Sync lead 97 (kabir.nair97@example.com). The API replies 201 with id `1096`.
  2. Request `GET http://127.0.0.1:8765/crm/v3/objects/contacts/1096`.
  3. Expected: 200 with the contact. Actual: 404.

## BUG-002: Long company names are truncated
- Affected leads: 13
- Reproduction:
  1. Create a contact with company `International Business Solutions and Consulting Pvt Ltd`.
  2. Read it back with `GET http://127.0.0.1:8765/crm/v3/objects/contacts/1039`.
  3. Expected the full name. Actual: `International Business Solutio` (cut at 30 characters).

## BUG-003: Phone numbers with an extension are wiped
- Affected leads: 10
- Reproduction:
  1. Create a contact with phone `+917289482182 x123`.
  2. Read it back with `GET http://127.0.0.1:8765/crm/v3/objects/contacts/1049`.
  3. Expected the phone number. Actual: empty string.