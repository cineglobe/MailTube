from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from mailtube.api.app import create_app
from mailtube.config import Settings
from mailtube.security.auth import AuthService


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        work_dir=tmp_path / "work",
        static_dir=tmp_path / "static",
        allowed_hosts=["testserver"],
        admin_password_hash=SecretStr(AuthService.hash_password("correct horse battery")),
        session_secret=SecretStr("s" * 48),
        cleanup_interval_seconds=60,
    )


def test_auth_csrf_jobs_and_security_headers(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        unauthorized = client.get("/api/v1/jobs")
        assert unauthorized.status_code == 401
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct horse battery"},
        )
        assert login.status_code == 200
        assert login.cookies.get("mailtube_session")
        assert login.headers["x-frame-options"] == "DENY"
        csrf = login.json()["csrf_token"]
        payload = {
            "items": [
                {
                    "url": "https://youtu.be/dQw4w9WgXcQ",
                    "format": "mp3",
                    "quality": "192k",
                }
            ]
        }
        rejected = client.post("/api/v1/jobs", json=payload)
        assert rejected.status_code == 403
        created = client.post(
            "/api/v1/jobs",
            json=payload,
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "same"},
        )
        repeated = client.post(
            "/api/v1/jobs",
            json=payload,
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "same"},
        )
        assert created.status_code == 202
        assert created.json() == repeated.json()


def test_rejects_lookalike_host(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct horse battery"},
        )
        response = client.post(
            "/api/v1/jobs",
            json={
                "items": [
                    {
                        "url": "https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ",
                        "format": "mp4",
                        "quality": "720p",
                    }
                ]
            },
            headers={"X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert response.status_code == 422


def test_unknown_api_and_frontend_paths_do_not_fall_back_to_index(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("root")
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/unknown").status_code == 404
        assert client.get("/definitely-not-a-route").status_code == 404


def test_email_diagnostic_is_a_csrf_protected_post(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct horse battery"},
        )
        assert client.get("/api/v1/diagnostics/email").status_code == 404
        assert client.post("/api/v1/diagnostics/email").status_code == 403
        response = client.post(
            "/api/v1/diagnostics/email",
            headers={"X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": False, "detail": "Email integration is disabled"}


def test_runtime_settings_are_encrypted_and_survive_restart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct horse battery"},
        )
        response = client.patch(
            "/api/v1/settings",
            json={
                "poll_interval_seconds": 15,
                "imap_host": "imap.example.test",
                "imap_password": "private-app-password",
                "max_concurrent_jobs": 2,
            },
            headers={"X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert response.status_code == 200
        stored = client.app.state.mailtube.db.get_runtime_settings()
        assert stored["_secret_imap_password"].startswith("enc:v1:")
        assert "private-app-password" not in stored["_secret_imap_password"]

    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct horse battery"},
        )
        response = client.get("/api/v1/settings")
        payload = response.json()
        assert response.status_code == 200
        assert payload["imap_host"] == "imap.example.test"
        assert payload["poll_interval_seconds"] == 15
        assert payload["max_concurrent_jobs"] == 2
        assert payload["has_imap_password"] is True
        assert "imap_password" not in payload
