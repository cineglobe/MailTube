import pytest

from mailtube.security.runtime_secrets import (
    RuntimeSecretError,
    open_runtime_secret,
    seal_runtime_secret,
)


def test_runtime_secret_round_trip_and_authentication() -> None:
    sealed = seal_runtime_secret("gmail-app-password", "s" * 48, "instance")
    assert "gmail-app-password" not in sealed
    assert open_runtime_secret(sealed, "s" * 48, "instance") == "gmail-app-password"

    with pytest.raises(RuntimeSecretError):
        open_runtime_secret(f"{sealed[:-1]}A", "s" * 48, "instance")
