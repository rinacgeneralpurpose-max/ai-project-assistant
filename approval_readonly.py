"""Phase 4B: short-lived signed review tokens and conflict checks. No writes."""
import base64
import hashlib
import hmac
import json
import os
import time
from update_preview import preview_update

TTL_SECONDS = 600

def _secret():
    secret = os.environ.get("APPROVAL_SIGNING_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("APPROVAL_SIGNING_KEY must be at least 32 characters")
    return secret.encode("utf-8")

def _encode(data):
    return base64.urlsafe_b64encode(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")

def _decode(data):
    return json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))

def create_review(data):
    preview, code = preview_update(data)
    if code != 200:
        return preview, code
    token_data = {"project_id": preview["project_id"],
                  "transcript": preview["transcript"],
                  "changes": {k: v["proposed"] for k, v in preview["proposed_changes"].items()},
                  "current": {k: v["current"] for k, v in preview["proposed_changes"].items()},
                  "expires_at": int(time.time()) + TTL_SECONDS}
    encoded = _encode(token_data)
    signature = hmac.new(_secret(), encoded.encode(), hashlib.sha256).hexdigest()
    return {"status": "review_required", "review_token": encoded + "." + signature,
            "expires_at": token_data["expires_at"], "preview": preview,
            "writes_enabled": False}, 200

def validate_approval(data):
    if not isinstance(data, dict) or data.get("approve") is not True:
        return {"status": "invalid_request", "reason": "Explicit approve=true required"}, 400
    token = data.get("review_token")
    if not isinstance(token, str) or len(token) > 16000 or "." not in token:
        return {"status": "invalid_request", "reason": "Invalid review token"}, 400
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(_secret(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return {"status": "unauthorized", "reason": "Invalid signature"}, 401
    try:
        claims = _decode(encoded)
        if not isinstance(claims, dict) or not isinstance(claims.get("expires_at"), int):
            raise ValueError("Invalid token")
        if int(time.time()) >= claims["expires_at"]:
            return {"status": "expired", "reason": "Review token expired"}, 409
        preview, code = preview_update({"project_id": claims["project_id"],
                                        "transcript": claims["transcript"],
                                        "changes": claims["changes"]})
        if code != 200:
            return {"status": "conflict", "reason": "Project no longer available"}, 409
        for field, old in claims["current"].items():
            if preview["proposed_changes"][field]["current"] != old:
                return {"status": "conflict", "reason": "Project changed since review; request a new review"}, 409
    except (ValueError, KeyError, TypeError, UnicodeError):
        return {"status": "invalid_request", "reason": "Malformed review token"}, 400
    return {"status": "approval_validated", "project_id": claims["project_id"],
            "proposed_changes": preview["proposed_changes"], "writes_enabled": False,
            "note": "Approval validation only. No Google Sheets mutation or audit write performed."}, 200
