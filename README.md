# QNAB Onboarding Automation

Flask web service for the two APE-specific Bonita automation use cases:

1. **Signed Contract Recording** — HR uploads a scanned, physically signed contract in Bonita; Flask links the existing signed document to the correct case and updates the contract status through Bonita.
2. **Finance Form Collection** — Bonita requests an online finance form for an APE employee; Flask emails a unique link, validates submission, and writes structured data to the same Bonita case before payroll processing continues.

**Status:** Initial project scaffold. Bonita document and BDM mappings must be verified before claiming end-to-end integration. Do not submit real employee, contract, or banking data to a development server.

## Integration design

Bonita remains the system of record. The Flask service never assumes the names of Bonita BDM attributes and will not mark an automation successful unless the corresponding Bonita API operation succeeds.

Credentials are configured using environment variables and must never be committed to this repository.
