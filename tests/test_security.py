from messenger_ai.security import meta_signature_header, verify_meta_signature


def test_meta_signature_roundtrip():
    secret = "app-secret"
    body = b'{"object":"instagram"}'
    header = meta_signature_header(secret, body)
    assert verify_meta_signature(secret, body, header) is True
    assert verify_meta_signature(secret, body, "sha256=deadbeef") is False
    assert verify_meta_signature(secret, body, None) is False
    assert verify_meta_signature("", body, None) is True
