"""Auth locale, volutamente sostituibile.

Il brief (§12) lascia aperta la scelta tra utenti propri e login Google
aziendale. La versione 1 usa utenti propri: email, password e un cookie
di sessione firmato. I router non conoscono il meccanismo, chiedono solo
`get_current_user`. Per passare a Google basta un altro backend che
emette lo stesso cookie (o sostituisce `leggi_sessione`) e popola `utente`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta

from mosaika.timeutil import adesso

COOKIE = "mosaika_session"
RUOLI = ("commerciale", "tecnico", "admin")
VALIDATORI = ("tecnico", "admin")
# Il sopralluogo in campo lo compila chi misura. Il commerciale legge ed esporta.
SCRITTORI_SOPRALLUOGO = VALIDATORI


def hash_password(password: str, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return "pbkdf2_sha256$%d$%s$%s" % (
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(hash_b64.encode("ascii"))
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iters)
        )
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def firma_sessione(utente_id: int, secret: str, giorni: int) -> str:
    payload = {
        "uid": utente_id,
        "exp": int((adesso() + timedelta(days=giorni)).timestamp()),
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{body}.{signature}"


def leggi_sessione(token: str | None, secret: str) -> int | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(
        secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    padding = "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + padding))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(adesso().timestamp()):
        return None
    uid = payload.get("uid")
    return int(uid) if uid else None


def puo_validare(ruolo: str) -> bool:
    return ruolo in VALIDATORI


def puo_scrivere_sopralluogo(ruolo: str) -> bool:
    return ruolo in SCRITTORI_SOPRALLUOGO
