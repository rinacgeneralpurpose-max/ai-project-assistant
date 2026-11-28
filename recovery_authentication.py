"""Google OIDC verification for *recovery review* only.

No API route or Sheets write is enabled. Google account subjects must be
explicitly allowlisted by server-side configuration, not client claims.
"""
from dataclasses import dataclass


class RecoveryAuthenticationDenied(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedRecoveryReviewer:
    subject: str


def _google_verify(token, audience):
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    # Google's library checks signature, token expiry and expected audience.
    return id_token.verify_oauth2_token(token, Request(), audience=audience)


def verify_recovery_reviewer(*, token, audience, allowed_subjects, verifier=None):
    """Return allowlisted Google subject after verified OIDC ID-token check.

    'verifier' is injectable for offline tests only. A real deployment must
    never choose a verifier based on user input or bypass signature validation.
    """
    if not isinstance(token, str) or not token.strip():
        raise RecoveryAuthenticationDenied("Valid identity token required")
    if not isinstance(audience, str) or not audience.strip():
        raise RecoveryAuthenticationDenied("OIDC client audience is not configured")
    if not isinstance(allowed_subjects, (set, frozenset, tuple, list)):
        raise RecoveryAuthenticationDenied("Reviewer allowlist is not configured")
    allowed = {s for s in allowed_subjects if isinstance(s, str) and s.strip()}
    if not allowed:
        raise RecoveryAuthenticationDenied("Recovery reviewers not configured")
    try:
        claims = (verifier or _google_verify)(token, audience)
    except Exception:
        raise RecoveryAuthenticationDenied("Identity verification failed") from None
    if not isinstance(claims, dict):
        raise RecoveryAuthenticationDenied("Invalid identity claims")
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise RecoveryAuthenticationDenied("Untrusted token issuer")
    if claims.get("aud") != audience:
        raise RecoveryAuthenticationDenied("Token audience mismatch")
    if claims.get("email_verified") is not True:
        raise RecoveryAuthenticationDenied("Unverified account")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip() or subject not in allowed:
        raise RecoveryAuthenticationDenied("Recovery reviewer not authorized")
    return VerifiedRecoveryReviewer(subject=subject)
