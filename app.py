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
    """Bonita APE branch invokes this endpoint with the case ID and employee email."""
    if not access_allowed():
        return fail("Unauthorized", 401)
    body = request.get_json(silent=True) or {}
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
        link = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/") + "/finance/" + token
        email_invitation(recipient, link)
        invitations[token] = {"case_id": case_id, "email": recipient, "submitted": False}
        return jsonify({"case_id": case_id, "email_sent": True}), 200
    except (BonitaError, RuntimeError, OSError, smtplib.SMTPException):
        app.logger.exception("Unable to send finance form invitation")
        return fail("Finance invitation failed; see server logs", 502)


FORM = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QNAB Finance Form</title><style>
body{font:16px system-ui;max-width:550px;margin:3rem auto;padding:1rem;color:#264f42}
label{display:block;margin:1rem 0}input{display:block;width:100%;padding:.65rem;box-sizing:border-box}
button{background:#264f42;color:white;padding:.8rem 1.4rem;border:0;border-radius:5px}
</style></head><body><h1>Employee Finance Form</h1>
<p>Prototype only — use fictional bank details, not real ones.</p>
<form method="post">
<label>Account holder name<input name="account_name" required maxlength="100"></label>
<label>Bank name<input name="bank_name" required maxlength="100"></label>
<label>BSB (6 digits)<input name="bsb" pattern="[0-9]{6}" required></label>
<label>Account number (4–12 digits)<input name="account_number" pattern="[0-9]{4,12}" required></label>
<button type="submit">Submit</button></form></body></html>"""


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
        record["submitted"] = True
        return "Finance details submitted to Bonita successfully.", 200
    except (BonitaError, KeyError):
        app.logger.exception("Bonita finance case update failed")
        return "Unable to save data to Bonita. Please retry.", 502


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
