from app.crypto import encrypt_str, decrypt_str


def test_encrypt_decrypt_roundtrip():
    original = "user@example.com"
    token = encrypt_str(original)
    assert token != original
    out = decrypt_str(token)
    assert out == original
