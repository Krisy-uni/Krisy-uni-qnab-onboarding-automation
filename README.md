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

{"case_id": 123, "email": "ape.example@example.test"}
```

Flask sends a unique link using the SMTP settings. The employee completes an online form; Flask validates entries and updates two pre-existing **string process variables** in the correct Bonita case: the JSON-formatted finance data and the readiness flag. The workflow **must wait** for the successful submission before Finance creates the payroll profile. This waiting/gateway logic is part of the Bonita BPMN and has **not** been implemented by the Flask web service. DBY remains unchanged.

**Important:** The current form is a demonstration prototype, not a secure production payroll solution. Use **fictional finance information only**. Before real deployment, use HTTPS, persistent expiring single-use invitation tokens, appropriate access controls, a secure BDM/schema for finance records, audit logging without sensitive data, and appropriate payroll privacy/security controls. Do not put real bank details in a general-purpose string case variable.


## Bonita Studio progress (24 October 2026)

The simplified process **QNAB Automation - APE** currently has this path:

1. Prepare Employment Contract (Legal Team human task)
2. Send physical Contract to Employee (HR human task)
3. Receive and Upload Signed Contract (HR human task)
4. Register Signed Contract (service task; REST POST `/api/contracts/register`)
5. Create Staff Number (HR human task)
6. Send Finance Form Link (service task; REST POST `/api/finance/invite`)
7. Create Payroll Profile (Finance human task)
8. End

The intermediate finance message catch event was removed to keep the demonstration focused. **This means the payroll task is currently reached immediately after the invitation service task, not automatically held until form submission.** The finance-submission prerequisite still requires an enforceable check before the process can be called end-to-end complete.

### Configured Bonita data and forms

- Imported BDM package `com.qnab.onboarding` with `Contract`, `KycDeclaration`, `Offer`, `OnboardingCase`, and `Prospect`.
- Business variables `onboardingCase` and `prospect` initialized using their respective DAO `newInstance()` methods.
- Legal task `Prepare Employment Contract` has a `prospectInput` complex contract, with six auto-generated update operations: firstName, lastName, preferredName, dateOfBirth, email, phone. The generated UI Designer form's `formOutput` maps these fields into `prospectInput`.
- Process document `signedContract` was created for HR to upload the scanned signed contract. Verify its upload form and document operation in a live run.
- Finance invitation connector payload configured to send `case_id` and `email` from `processInstanceId` and `prospect.email`. Flask accepts either `email` or `employee_email` as of this update.

### Outstanding integration checks

- **Authentication:** Flask POST endpoints require `X-Integration-Key`. The Bonita REST connector must send this header; otherwise Flask returns HTTP 401. Do not place real secrets in this public repository.
- **BDM mapping:** Flask contract endpoint currently writes STRING case variables rather than `Contract.signedornot`. Finance submission similarly writes STRING case variables rather than `OnboardingCase.financeDetailsReceived` or a secure finance-data business object. These are **not equivalent** and must be mapped/implemented before claiming the BDM is updated.
- **Data completeness:** Current `Contract` BDM fields do not include a contract PDF reference. Document linkage must be verified through the Bonita process document or a suitable business mapping.
- **Finance ordering:** Without the removed message catch event, the payroll task needs a verified guard/validation before completion. Do not claim Bonita automatically waits for employee submission.
- **Runtime:** Resolve the remaining red Bonita validation markers, configure local Flask/SMTP and Bonita API credentials, and perform actual end-to-end tests. No successful live test has been established yet.
- **Privacy:** Finance form is demonstration-only. Use fictional bank details; do not use real payroll information in this prototype.

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
