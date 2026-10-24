# QNAB — Bonita + Flask Automation

This repository implements the external web-service portion of the two APE onboarding scenarios. **The Bonita BPMN and existing data mappings must also be configured.** This is not yet an end-to-end validated deployment.

## Use Case 1 — Signed Contract Recording

Bonita HR task `Upload signed contract` saves a process document named `signedContract`. The following Bonita service task calls:

```http
POST http://127.0.0.1:5000/api/contracts/register
Content-Type: application/json
X-Integration-Key: <configured-shared-key>

{"case_id": 123}
```

Flask authenticates to Bonita, checks the case exists, obtains the signed document metadata, then writes the document ID and `SIGNED` status into two **existing string process variables** defined in `.env`. It does not perform OCR, modify the PDF, or re-enter contract details. The **document remains stored in Bonita**, not a second Flask database.

If the requirement is to update an existing **BDM Contract business object**, the BPMN task must use these output variables to update the business object via a task operation, or a version-appropriate business data API. Do not treat process variables as equivalent to BDM field updates.

## Use Case 2 — Finance Form Collection

After staff number creation, use the **APE branch only** to call:

```http
POST http://127.0.0.1:5000/api/finance/invite
Content-Type: application/json
X-Integration-Key: <configured-shared-key>

{"case_id": 123, "employee_email": "ape.example@example.test"}
```

Flask sends a unique link using the SMTP settings. The employee completes an online form; Flask validates entries and updates two pre-existing **string process variables** in the correct Bonita case: the JSON-formatted finance data and the readiness flag. The workflow **must wait** for the successful submission before Finance creates the payroll profile. This waiting/gateway logic is part of the Bonita BPMN and has **not** been implemented by the Flask web service. DBY remains unchanged.

**Important:** The current form is a demonstration prototype, not a secure production payroll solution. Use **fictional finance information only**. Before real deployment, use HTTPS, persistent expiring single-use invitation tokens, appropriate access controls, a secure BDM/schema for finance records, audit logging without sensitive data, and appropriate payroll privacy/security controls. Do not put real bank details in a general-purpose string case variable.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Edit `.env` with your local Bonita credentials and the **actual names** of the variables you create or find in Bonita. Do **not** commit `.env`.

Health check: `http://127.0.0.1:5000/health`.

Run unit tests:

```bash
pytest -q
```

## Files

- `app.py`: Flask HTTP endpoints, email invitations and online form.
- `bonita_client.py`: Bonita authenticated REST client.
- `.env.example`: required mapping and credentials template.
- `tests/test_app.py`: initial HTTP input/auth checks.

## Remaining integration work (required)

1. Confirm actual Bonita Studio BPMN/BDM fields and process variable names.
2. Create/verify the two contract process variables and two finance process variables; map BDM operations rather than guessing BDM fields.
3. Configure Bonita REST connectors to pass case ID / email and the integration key; ensure case document is attached by the HR human task.
4. Implement the Bonita waiting/continuation mechanism for finance submission.
5. Configure SMTP and verify the email delivery path.
6. Run full tests in Bonita and record the assessment demonstration.
