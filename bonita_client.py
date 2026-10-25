"""Narrow Bonita REST API client; business mappings are configured explicitly."""
import requests


class BonitaError(Exception):
    pass


class BonitaClient:
    def __init__(self, url, user, password):
        if not all((url, user, password)):
            raise BonitaError("Bonita URL and credentials must be configured")
        self.base = url.rstrip("/")
        self.session = requests.Session()
        try:
            response = self.session.post(
                self.base + "/loginservice",
                data={"username": user, "password": password, "redirect": "false"},
                timeout=15,
            )
            response.raise_for_status()
            if not self.session.cookies.get("JSESSIONID"):
                raise BonitaError("Bonita login did not establish a session")
            token = self.session.cookies.get("X-Bonita-API-Token")
            if token:
                self.session.headers.update({"X-Bonita-API-Token": token})
        except requests.RequestException as exc:
            raise BonitaError("Bonita authentication failed") from exc

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.session.close()

    def request(self, method, path, **kwargs):
        try:
            result = self.session.request(
                method, self.base + "/API/" + path.lstrip("/"), timeout=15, **kwargs
            )
            print("BONITA API:", method, path, "STATUS:", result.status_code, "RESPONSE:", result.text[:500], flush=True)
            result.raise_for_status()
            return result.json() if result.content else None
        except (requests.RequestException, ValueError) as exc:
            raise BonitaError("Bonita REST API operation failed") from exc

    def case(self, case_id):
        return self.request("GET", f"bpm/case/{case_id}")

    def case_documents(self, case_id):
        return self.request("GET", "bpm/caseDocument", params={
            "p": 0, "c": 100, "f": f"caseId={case_id}"
        })

    def variable(self, case_id, name):
        return self.request("GET", f"bpm/caseVariable/{case_id}/{name}")

    def put_string_variable(self, case_id, name, value):
        # Bonita case variable API supports Java String (not arbitrary BDM objects).
        existing = self.variable(case_id, name)
        if existing.get("type") != "java.lang.String":
            raise BonitaError(f"Case variable {name} is not java.lang.String")
        return self.request("PUT", f"bpm/caseVariable/{case_id}/{name}",
                            json={"type": "java.lang.String", "value": value})
    def send_message(self, case_id):
        payload = {
            "messageName": "FinanceFormSubmitted",
            "targetProcess": "QNAB Automation- APE",
            "correlations": {
                "caseId": {
                    "type": "java.lang.String",
                    "value": str(case_id)
                }
            }
        }
        return self.request(
            "POST",
            "bpm/message",
            json=payload
        )