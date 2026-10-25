"""QNAB APE onboarding automation. Only fictitious test data in development."""
import json
import os
import re
import secrets
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template_string, request, session

from bonita_client import BonitaClient, BonitaError

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

# Prototype: in-memory invitations, intentionally no bank details persisted locally.
# Restarting Flask invalidates pending links. Replace with persistent token storage
# if deploying beyond a short controlled demonstration.
invitations = {}
FORM = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>QNAB Employee Finance Form</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f5f6f8;
            padding: 40px;
        }
        .container {
            max-width: 480px;
            margin: auto;
            padding: 30px;
            background: white;
            border-radius: 10px;
        }
        label {
            display: block;
            margin-top: 18px;
        }
        input {
            width: 100%;
            padding: 10px;
            box-sizing: border-box;
            margin-top: 6px;
        }
        button {
            margin-top: 24px;
            padding: 12px;
            width: 100%;
            background: #245b47;
            color: white;
            border: none;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>QNAB Employee Finance Form</h2>
        <p>Please provide your bank details for payroll setup.</p>

        <form method="POST">
            <label>Account Name</label>
            <input name="account_name" required>

            <label>Bank Name</label>
            <input name="bank_name" required>

            <label>BSB (6 digits)</label>
            <input name="bsb" pattern="[0-9]{6}" required>

            <label>Account Number</label>
            <input name="account_number" pattern="[0-9]{4,12}" required>

            <button type="submit">Submit Finance Details</button>
        </form>
    </div>
</body>
</html>
"""

def fail(message, status=400):
    return jsonify({"error": message}), status


def access_allowed():
    expected = os.getenv("INTEGRATION_API_KEY", "")
    provided = request.headers.get("X-Integration-Key", "")
    return bool(expected) and secrets.compare_digest(expected, provided)


def bonita():
    return BonitaClient(os.getenv("BONITA_URL", ""),
                        os.getenv("BONITA_USER", ""),
                        os.getenv("BONITA_PASSWORD", ""))


def positive_id(value):
    text = str(value or "")
    return int(text) if text.isdecimal() and int(text) > 0 else None


@app.get("/health")
def health():
    return jsonify({"status": "ok", "integration": "not_verified"})


@app.post("/api/contracts/register")
def register_contract():
    """Register an existing Bonita signed PDF, without OCR or re-entering details."""
    if not access_allowed():
        return fail("Unauthorized", 401)
    body = request.get_json(silent=True) or {}
    case_id = positive_id(body.get("case_id"))
    if not case_id:
        return fail("case_id is required")
    status_var = os.getenv("CONTRACT_STATUS_VARIABLE", "")
    document_var = os.getenv("CONTRACT_DOCUMENT_ID_VARIABLE", "")
    if not status_var or not document_var:
        return fail("Bonita contract variable mapping is not configured", 503)
    try:
        with bonita() as client:
            client.case(case_id)
            docs = client.case_documents(case_id)
            signed = [d for d in docs if d.get("name") == "signedContract"]
            if not signed:
                return fail("signedContract was not found in this Bonita case", 422)
            doc_id = str(signed[-1]["id"])
            # Make the Bonita document link available as a process variable.
            client.put_string_variable(case_id, document_var, doc_id)
            client.put_string_variable(case_id, status_var, "SIGNED")
            return jsonify({"case_id": case_id, "document_id": doc_id,
                            "status": "SIGNED", "registered": True})
    except BonitaError:
        app.logger.exception("Failed to register signed contract in Bonita")
        return fail("Bonita update failed; see server logs", 502)


def email_invitation(recipient, link):
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM must be configured")
    message = EmailMessage()
    message["Subject"] = "QNAB employee finance form"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("Please complete your finance details using this link:\n" + link)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
        if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        if os.getenv("SMTP_USER"):
            smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(message)


@app.post("/api/finance/invite")
def finance_invite():
    """Bonita invokes this endpoint with the case ID and employee email."""
    if not access_allowed():
        return fail("Unauthorized", 401)

    body = request.get_json(silent=True) or {}
    print("FINANCE INVITE DEBUG:", "content_type=", request.content_type, "body=", body, flush=True)
    case_id = positive_id(body.get("case_id"))
    recipient = str(body.get("employee_email") or body.get("email") or "").strip()

    if not case_id or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        return fail("Valid case_id and employee_email required")

    if not os.getenv("FINANCE_DATA_VARIABLE") or not os.getenv("FINANCE_READY_VARIABLE"):
        return fail("Finance case variable mappings are not configured", 503)

    try:
        with bonita() as client:
            client.case(case_id)

        token = secrets.token_urlsafe(32)
        link = os.getenv(
            "PUBLIC_BASE_URL", "http://localhost:5001"
        ).rstrip("/") + "/finance/" + token

        invitations[token] = {
            "case_id": case_id,
            "email": recipient,
            "submitted": False
        }
        print("FINANCE FORM LINK:", link, flush=True)
        return jsonify({
            "case_id": case_id,
            "email_sent": False,
            "form_link": link
        }), 200

    except (BonitaError, RuntimeError, OSError, smtplib.SMTPException):
        app.logger.exception("Unable to create finance form invitation")
        return fail("Finance invitation failed; see server logs", 502)
@app.route("/finance/<token>", methods=["GET", "POST"])
def finance_form(token):
    record = invitations.get(token)
    if record is None:
        abort(404)
    if record["submitted"]:
        return "This form has already been submitted.", 200
    if request.method == "GET":
        return render_template_string(FORM)
    data = {field: request.form.get(field, "").strip()
            for field in ("account_name", "bank_name", "bsb", "account_number")}
    if not data["account_name"] or not data["bank_name"] or not re.fullmatch(r"\d{6}", data["bsb"]) or not re.fullmatch(r"\d{4,12}", data["account_number"]):
        return "Please provide valid details.", 400
    try:
        with bonita() as client:
            case_id = record["case_id"]
            client.case(case_id)
            # Existing *string process variables* must be mapped before first use.
            # The BPMN gateway must read financeReady == "true" before payroll.
            # A Java business object (BDM) requires task operations or a mapped API.
            client.put_string_variable(case_id, os.environ["FINANCE_DATA_VARIABLE"],
                                       json.dumps(data))
            client.put_string_variable(case_id, os.environ["FINANCE_READY_VARIABLE"], "true")
            client.send_message(case_id)
        record["submitted"] = True
        return "Finance details submitted to Bonita successfully.", 200
    except (BonitaError, KeyError):
        app.logger.exception("Bonita finance case update failed")
        return "Unable to save data to Bonita. Please retry.", 502
@app.get("/finance-preview")
def finance_preview():
    return FORM
@app.get("/test-finance-link/<int:case_id>")
def test_finance_link(case_id):
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)

    with bonita() as client:
        client.case(case_id)

    token = secrets.token_urlsafe(32)
    invitations[token] = {
        "case_id": case_id,
        "email": "demo@example.com",
        "submitted": False
    }
    
    return jsonify({
        "case_id": case_id,
        "form_link": "http://localhost:5001/finance/" + token
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
