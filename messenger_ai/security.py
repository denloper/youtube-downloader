import hashlib
import hmac


def verify_meta_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not app_secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    received = header.split("=", 1)[1].strip()
    return hmac.compare_digest(expected, received)


def meta_signature_header(app_secret: str, body: bytes) -> str:
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"
