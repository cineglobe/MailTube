from __future__ import annotations

import base64
import hashlib
import secrets

from Cryptodome.Cipher import AES

PREFIX = "enc:v1:"


class RuntimeSecretError(ValueError):
    """Raised when an encrypted runtime secret cannot be authenticated."""


def _key(session_secret: str, instance_id: str) -> bytes:
    material = f"mailtube-runtime-settings\0{instance_id}\0{session_secret}".encode()
    return hashlib.sha256(material).digest()


def seal_runtime_secret(value: str, session_secret: str, instance_id: str) -> str:
    nonce = secrets.token_bytes(12)
    cipher = AES.new(_key(session_secret, instance_id), AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(value.encode())
    payload = base64.urlsafe_b64encode(nonce + tag + ciphertext).decode()
    return f"{PREFIX}{payload}"


def open_runtime_secret(value: str, session_secret: str, instance_id: str) -> str:
    if not value.startswith(PREFIX):
        raise RuntimeSecretError("Unsupported encrypted runtime secret")
    try:
        payload = base64.urlsafe_b64decode(value.removeprefix(PREFIX).encode())
        nonce, tag, ciphertext = payload[:12], payload[12:28], payload[28:]
        cipher = AES.new(_key(session_secret, instance_id), AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeSecretError("Encrypted runtime secret could not be authenticated") from exc
