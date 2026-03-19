import time
import requests
from engine.validator import normalize_value

MAX_RETRIES   = 3
RETRY_BACKOFF = 2


def build_form_url(prefilled_link):
    return prefilled_link.split("/viewform")[0] + "/formResponse"


def submit_row(row, required_columns, field_types, form_url, prefilled_link, max_retries=MAX_RETRIES):
    payload = {}
    for col, entry in required_columns.items():
        etype = field_types.get(entry, "text")
        value = normalize_value(row.get(col, ""), etype)
        if "," in value:
            payload[entry] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            payload[entry] = value
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":    prefilled_link,
        "Origin":     "https://docs.google.com",
    }
    session = requests.Session()
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(form_url, data=payload, headers=headers, timeout=30)
            if resp.status_code == 200 and (
                "Your response has been recorded" in resp.text or "formResponse" in resp.url
            ):
                return {"success": True,  "status_code": 200, "reason": "OK"}
            return {"success": False, "status_code": resp.status_code, "reason": f"HTTP {resp.status_code}"}
        except requests.exceptions.RequestException as exc:
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF * attempt)
            else:
                return {"success": False, "status_code": 0, "reason": str(exc)}
    return {"success": False, "status_code": 0, "reason": "Failed after max retries"}
