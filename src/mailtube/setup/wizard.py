from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from pydantic import SecretStr
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    Switch,
)

from mailtube.config import Settings
from mailtube.email.service import EmailService
from mailtube.security.auth import AuthService
from mailtube.storage import S3Storage


@dataclass
class SetupData:
    bind_mode: str = "tailscale"
    port: int = 8080
    public_url: str = "http://127.0.0.1:8080"
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1", "mailtube"])
    admin_username: str = "admin"
    admin_password: str = ""
    email_enabled: bool = False
    email_preset: str = "gmail"
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_security: str = "starttls"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    sender_policy: str = "allowlist"
    sender_allowlist: list[str] = field(default_factory=list)
    delivery_mode: str = "links"
    storage_backend: str = "s3"
    storage_preset: str = "r2"
    s3_endpoint: str = ""
    s3_region: str = "auto"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_force_path_style: bool = False
    resource_preset: str = "pi"
    max_urls: int = 5
    max_file_mb: int = 1024
    retention_hours: int = 24
    pot_provider: bool = False
    cookies_source: str = ""


class WizardScreen(Screen[None]):
    @property
    def setup_app(self) -> MailTubeSetupApp:
        return cast("MailTubeSetupApp", self.app)

    def nav(self, *, back: str | None = None, next_screen: str | None = None) -> Horizontal:
        buttons: list[Button] = []
        if back:
            buttons.append(Button("Back", id=f"go-{back}", variant="default"))
        if next_screen:
            buttons.append(Button("Continue", id=f"go-{next_screen}", variant="primary"))
        return Horizontal(*buttons, classes="actions")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("go-"):
            target = event.button.id.removeprefix("go-")
            self.capture()
            self.setup_app.push_screen(target)

    def capture(self) -> None:
        return None


class WelcomeScreen(WizardScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="page"):
            yield Static("MailTube", classes="wordmark")
            yield Static("Self-hosted conversion, without the mystery.", classes="headline")
            yield Static(
                "This wizard creates a private Docker deployment for web and email requests. "
                "Use MailTube only for media you are permitted to download. A residential network "
                "is recommended because datacenter IP addresses are frequently blocked by YouTube.",
                classes="copy",
            )
            yield self.nav(next_screen="preflight")
        yield Footer()


class PreflightScreen(WizardScreen):
    def compose(self) -> ComposeResult:
        architecture = platform.machine().lower()
        supported = architecture in {"x86_64", "amd64", "aarch64", "arm64"}
        usage = shutil.disk_usage(self.setup_app.config_dir.parent)
        yield Header()
        with Vertical(id="page"):
            yield Static("System preflight", classes="headline small")
            yield Static(
                f"Architecture: {architecture} ({'supported' if supported else 'unsupported'})\n"
                f"Free disk: {usage.free / (1024**3):.1f} GiB\n"
                "Docker and Compose are validated by the host installer before this wizard starts.",
                classes="review",
            )
            if not supported:
                yield Static("MailTube requires a 64-bit amd64 or arm64 host.", classes="status")
            yield self.nav(back="welcome", next_screen="access" if supported else None)
        yield Footer()


class AccessScreen(WizardScreen):
    def compose(self) -> ComposeResult:
        data = self.setup_app.data
        yield Header()
        with VerticalScroll(id="page"):
            yield Static("Access & administrator", classes="headline small")
            yield Label("Dashboard exposure")
            yield Select(
                [
                    ("Tailscale / localhost (recommended)", "tailscale"),
                    ("Local machine only", "localhost"),
                    ("Local network", "lan"),
                ],
                value=data.bind_mode,
                id="bind-mode",
            )
            yield Label("Port")
            yield Input(str(data.port), type="integer", id="port")
            yield Label("Public dashboard URL")
            yield Input(data.public_url, id="public-url")
            yield Label("Allowed hostnames (comma-separated)")
            yield Input(",".join(data.allowed_hosts), id="allowed-hosts")
            yield Label("Admin username")
            yield Input(data.admin_username, id="admin-username")
            yield Label("Admin password (12+ characters)")
            yield Input(password=True, id="admin-password")
            yield Label("Confirm password")
            yield Input(password=True, id="admin-confirm")
            yield Static("", id="access-status", classes="status")
            yield self.nav(back="welcome", next_screen="email")
        yield Footer()

    def capture(self) -> None:
        password = self.query_one("#admin-password", Input).value
        confirm = self.query_one("#admin-confirm", Input).value
        if len(password) < 12 or password != confirm:
            self.query_one("#access-status", Static).update(
                "Password must be at least 12 characters and both entries must match."
            )
            raise ValueError("Invalid administrator password")
        self.setup_app.data.bind_mode = str(self.query_one("#bind-mode", Select).value)
        self.setup_app.data.port = int(self.query_one("#port", Input).value)
        self.setup_app.data.public_url = self.query_one("#public-url", Input).value.strip()
        self.setup_app.data.allowed_hosts = [
            value.strip()
            for value in self.query_one("#allowed-hosts", Input).value.split(",")
            if value.strip()
        ]
        self.setup_app.data.admin_username = self.query_one("#admin-username", Input).value
        self.setup_app.data.admin_password = password

    def on_button_pressed(self, event: Button.Pressed) -> None:
        try:
            super().on_button_pressed(event)
        except ValueError:
            return


class EmailScreen(WizardScreen):
    def compose(self) -> ComposeResult:
        data = self.setup_app.data
        yield Header()
        with VerticalScroll(id="page"):
            yield Static("Email requests", classes="headline small")
            with Horizontal(classes="switch-row"):
                yield Switch(data.email_enabled, id="email-enabled")
                yield Label("Enable IMAP and SMTP")
            yield Label("Email provider")
            yield Select(
                [("Gmail App Password (recommended)", "gmail"), ("Generic IMAP/SMTP", "generic")],
                value=data.email_preset,
                id="email-preset",
            )
            yield Static(
                "Gmail preset: use a dedicated mailbox, enable 2-Step Verification, and create an App Password.",
                classes="copy compact",
            )
            yield Label("Email address")
            yield Input(data.imap_username, placeholder="mailtube@example.com", id="email-address")
            yield Label("App password")
            yield Input(password=True, id="email-password")
            yield Label("IMAP host and port")
            with Horizontal():
                yield Input(data.imap_host, id="imap-host")
                yield Input(str(data.imap_port), type="integer", id="imap-port")
            yield Label("SMTP host and port")
            with Horizontal():
                yield Input(data.smtp_host, id="smtp-host")
                yield Input(str(data.smtp_port), type="integer", id="smtp-port")
            yield Label("SMTP security")
            yield Select(
                [("STARTTLS", "starttls"), ("Implicit TLS", "tls")],
                value=data.smtp_security,
                id="smtp-security",
            )
            yield Label("Sender policy")
            yield Select(
                [("Allowlist only (recommended)", "allowlist"), ("Any sender", "any")],
                value=data.sender_policy,
                id="sender-policy",
            )
            yield Label("Allowed senders (comma-separated)")
            yield Input(",".join(data.sender_allowlist), id="sender-allowlist")
            with Horizontal(classes="actions"):
                yield Button("Test Gmail", id="test-email", variant="default")
            yield Static("", id="email-status", classes="status")
            yield self.nav(back="access", next_screen="storage")
        yield Footer()

    def capture(self) -> None:
        data = self.setup_app.data
        data.email_enabled = self.query_one("#email-enabled", Switch).value
        data.email_preset = str(self.query_one("#email-preset", Select).value)
        address = self.query_one("#email-address", Input).value.strip()
        password = self.query_one("#email-password", Input).value
        data.imap_username = data.smtp_username = data.smtp_from = address
        data.imap_password = data.smtp_password = password
        data.imap_host = self.query_one("#imap-host", Input).value.strip()
        data.imap_port = int(self.query_one("#imap-port", Input).value)
        data.smtp_host = self.query_one("#smtp-host", Input).value.strip()
        data.smtp_port = int(self.query_one("#smtp-port", Input).value)
        data.smtp_security = str(self.query_one("#smtp-security", Select).value)
        data.sender_policy = str(self.query_one("#sender-policy", Select).value)
        data.sender_allowlist = [
            value.strip().lower()
            for value in self.query_one("#sender-allowlist", Input).value.split(",")
            if value.strip()
        ]

    @work(thread=True, exclusive=True)
    def test_email(self) -> None:
        self.capture()
        data = self.setup_app.data
        if not data.email_enabled:
            self.setup_app.call_from_thread(
                self.query_one("#email-status", Static).update, "Email is disabled."
            )
            return
        settings = Settings(
            environment="test",
            email_enabled=True,
            imap_username=data.imap_username,
            imap_password=SecretStr(data.imap_password),
            smtp_username=data.smtp_username,
            smtp_password=SecretStr(data.smtp_password),
            smtp_from=data.smtp_from,
        )
        result = EmailService(settings, cast(Any, None), cast(Any, None)).test_connections()
        self.setup_app.call_from_thread(
            self.query_one("#email-status", Static).update, str(result["detail"])
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "test-email":
            self.test_email()
            return
        super().on_button_pressed(event)


class StorageScreen(WizardScreen):
    def compose(self) -> ComposeResult:
        data = self.setup_app.data
        yield Header()
        with VerticalScroll(id="page"):
            yield Static("Delivery & storage", classes="headline small")
            yield Label("Delivery mode")
            yield Select(
                [
                    ("Private S3 links (recommended)", "links"),
                    ("Small attachments + S3 overflow", "hybrid"),
                    ("Attachments only", "attachments"),
                ],
                value=data.delivery_mode,
                id="delivery-mode",
            )
            yield Label("S3 provider")
            yield Select(
                [
                    ("Cloudflare R2", "r2"),
                    ("Amazon S3", "aws"),
                    ("MinIO", "minio"),
                    ("Generic S3-compatible", "generic"),
                    ("Local files only", "local"),
                ],
                value=data.storage_preset,
                id="storage-preset",
            )
            yield Label("Endpoint URL")
            yield Input(
                data.s3_endpoint,
                placeholder="https://<account>.r2.cloudflarestorage.com",
                id="s3-endpoint",
            )
            yield Label("Region")
            yield Input(data.s3_region, id="s3-region")
            yield Label("Bucket")
            yield Input(data.s3_bucket, id="s3-bucket")
            yield Label("Access key ID")
            yield Input(data.s3_access_key_id, id="s3-key")
            yield Label("Secret access key")
            yield Input(password=True, id="s3-secret")
            with Horizontal(classes="actions"):
                yield Button("Test storage", id="test-storage", variant="default")
            yield Static("", id="storage-status", classes="status")
            yield self.nav(back="email", next_screen="policy")
        yield Footer()

    def capture(self) -> None:
        data = self.setup_app.data
        data.delivery_mode = str(self.query_one("#delivery-mode", Select).value)
        data.storage_preset = str(self.query_one("#storage-preset", Select).value)
        data.storage_backend = "local" if data.storage_preset == "local" else "s3"
        data.s3_endpoint = self.query_one("#s3-endpoint", Input).value.strip()
        data.s3_region = self.query_one("#s3-region", Input).value.strip() or "auto"
        data.s3_bucket = self.query_one("#s3-bucket", Input).value.strip()
        data.s3_access_key_id = self.query_one("#s3-key", Input).value.strip()
        data.s3_secret_access_key = self.query_one("#s3-secret", Input).value
        data.s3_force_path_style = data.storage_preset == "minio"
        if data.storage_preset == "minio":
            data.s3_endpoint = data.s3_endpoint or "http://minio:9000"
            data.s3_region = "us-east-1"

    @work(thread=True, exclusive=True)
    def test_storage(self) -> None:
        self.capture()
        data = self.setup_app.data
        if data.storage_backend == "local":
            self.setup_app.call_from_thread(
                self.query_one("#storage-status", Static).update, "Local storage selected."
            )
            return
        if data.storage_preset == "minio":
            self.setup_app.call_from_thread(
                self.query_one("#storage-status", Static).update,
                "The bundled MinIO sidecar will be tested after services start.",
            )
            return
        settings = Settings(
            environment="test",
            storage_backend="s3",
            s3_endpoint=data.s3_endpoint or None,
            s3_region=data.s3_region,
            s3_bucket=data.s3_bucket,
            s3_access_key_id=data.s3_access_key_id,
            s3_secret_access_key=SecretStr(data.s3_secret_access_key),
        )
        result = S3Storage(settings).test()
        self.setup_app.call_from_thread(
            self.query_one("#storage-status", Static).update, str(result["detail"])
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "test-storage":
            self.test_storage()
            return
        super().on_button_pressed(event)


class PolicyScreen(WizardScreen):
    def compose(self) -> ComposeResult:
        data = self.setup_app.data
        yield Header()
        with VerticalScroll(id="page"):
            yield Static("Limits & compatibility", classes="headline small")
            yield Label("Resource preset")
            yield Select(
                [
                    ("Raspberry Pi / 1 job", "pi"),
                    ("Balanced / 2 jobs", "balanced"),
                    ("Workstation / 4 jobs", "workstation"),
                ],
                value=data.resource_preset,
                id="resource-preset",
            )
            yield Label("Links per batch")
            yield Input(str(data.max_urls), type="integer", id="max-urls")
            yield Label("Maximum output size (MB)")
            yield Input(str(data.max_file_mb), type="integer", id="max-file")
            yield Label("Retention (hours)")
            yield Input(str(data.retention_hours), type="integer", id="retention")
            with Horizontal(classes="switch-row"):
                yield Switch(data.pot_provider, id="pot-provider")
                yield Label("Enable optional PO-token provider sidecar")
            yield Label("Optional Netscape cookie file on the Docker host")
            yield Input(
                data.cookies_source,
                placeholder="/home/user/.config/mailtube/youtube-cookies.txt",
                id="cookies-source",
            )
            yield self.nav(back="storage", next_screen="review")
        yield Footer()

    def capture(self) -> None:
        data = self.setup_app.data
        data.resource_preset = str(self.query_one("#resource-preset", Select).value)
        data.max_urls = max(1, min(25, int(self.query_one("#max-urls", Input).value)))
        data.max_file_mb = max(50, int(self.query_one("#max-file", Input).value))
        data.retention_hours = max(1, min(168, int(self.query_one("#retention", Input).value)))
        data.pot_provider = self.query_one("#pot-provider", Switch).value
        data.cookies_source = self.query_one("#cookies-source", Input).value.strip()


class ReviewScreen(WizardScreen):
    def compose(self) -> ComposeResult:
        data = self.setup_app.data
        yield Header()
        with VerticalScroll(id="page"):
            yield Static("Review", classes="headline small")
            yield Static(
                f"Bind: {data.bind_mode} · Port: {data.port}\n"
                f"Admin: {data.admin_username}\n"
                f"Email: {'enabled' if data.email_enabled else 'disabled'} · Sender policy: {data.sender_policy}\n"
                f"Delivery: {data.delivery_mode} · Storage: {data.storage_backend}\n"
                f"Preset: {data.resource_preset} · Retention: {data.retention_hours} hours",
                classes="review",
            )
            yield Static(
                "Secrets are masked and written with owner-only permissions. Switching to any-sender mode can expose your instance to abuse.",
                classes="copy compact",
            )
            with Horizontal(classes="actions"):
                yield Button("Back", id="go-policy")
                yield Button("Write configuration", id="save", variant="primary")
            yield Static("", id="save-status", classes="status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            path = self.setup_app.write_configuration()
            self.query_one("#save-status", Static).update(f"Configuration written to {path}")
            self.app.exit(str(path))
            return
        super().on_button_pressed(event)


class MailTubeSetupApp(App[str]):
    TITLE = "MailTube setup"
    CSS = """
    Screen { background: #101215; color: #f7f4ec; }
    Header { background: #0757ee; color: white; }
    #page { width: 76; max-width: 92%; height: 1fr; margin: 2 12; padding: 1 2; }
    .wordmark { color: #f7f4ec; text-style: bold; text-align: left; height: 3; }
    .headline { color: #ffffff; text-style: bold; height: auto; margin-bottom: 1; }
    .headline.small { margin-bottom: 2; }
    .copy { color: #b8b5ad; height: auto; margin-bottom: 2; }
    .copy.compact { margin: 1 0; }
    Label { margin-top: 1; }
    Input, Select { margin-bottom: 1; }
    .actions { height: auto; margin-top: 2; align-horizontal: right; }
    .actions Button { margin-left: 1; }
    .switch-row { height: 3; align-vertical: middle; }
    .switch-row Label { margin: 0 0 0 1; }
    .status { color: #ff7b63; height: auto; margin-top: 1; }
    .review { border: solid #4e535b; padding: 1 2; height: auto; }
    """
    SCREENS = {
        "welcome": WelcomeScreen,
        "preflight": PreflightScreen,
        "access": AccessScreen,
        "email": EmailScreen,
        "storage": StorageScreen,
        "policy": PolicyScreen,
        "review": ReviewScreen,
    }

    def __init__(self, config_dir: Path) -> None:
        super().__init__()
        self.config_dir = config_dir
        self.data = SetupData()

    def on_mount(self) -> None:
        self.push_screen("welcome")

    def write_configuration(self) -> Path:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = self.data
        concurrency = {"pi": 1, "balanced": 2, "workstation": 4}[data.resource_preset]
        bind = "127.0.0.1" if data.bind_mode in {"tailscale", "localhost"} else "0.0.0.0"
        image = os.getenv("MAILTUBE_IMAGE", "ghcr.io/OWNER/MailTube:latest")
        instance_id = secrets.token_hex(8)
        secret_values = {
            "admin_password_hash": AuthService.hash_password(data.admin_password),
            "session_secret": secrets.token_urlsafe(48),
            "imap_password": data.imap_password,
            "smtp_password": data.smtp_password,
            "s3_secret_access_key": data.s3_secret_access_key,
        }
        secrets_dir = self.config_dir / "secrets"
        secrets_dir.mkdir(mode=0o700, exist_ok=True)
        secrets_dir.chmod(0o700)
        for name, value in secret_values.items():
            secret_path = secrets_dir / name
            secret_path.write_text(value, encoding="utf-8")
            secret_path.chmod(0o600)
        empty_cookies = secrets_dir / "empty-cookies.txt"
        empty_cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        empty_cookies.chmod(0o600)
        env_values: dict[str, Any] = {
            "MAILTUBE_IMAGE": image,
            "MAILTUBE_DEPLOYMENT_MODE": data.bind_mode,
            "MAILTUBE_BIND_ADDRESS": bind,
            "MAILTUBE_HTTP_PORT": data.port,
            "MAILTUBE_HOST": "0.0.0.0",
            "MAILTUBE_PORT": 8080,
            "MAILTUBE_PUBLIC_URL": data.public_url,
            "MAILTUBE_ALLOWED_HOSTS": ",".join(data.allowed_hosts),
            "MAILTUBE_SECURE_COOKIES": str(data.public_url.startswith("https://")).lower(),
            "MAILTUBE_INSTANCE_ID": instance_id,
            "MAILTUBE_ADMIN_USERNAME": data.admin_username,
            "MAILTUBE_ADMIN_PASSWORD_HASH_FILE": "/run/secrets/admin_password_hash",
            "MAILTUBE_SESSION_SECRET_FILE": "/run/secrets/session_secret",
            "MAILTUBE_EMAIL_ENABLED": str(data.email_enabled).lower(),
            "MAILTUBE_IMAP_HOST": data.imap_host,
            "MAILTUBE_IMAP_PORT": data.imap_port,
            "MAILTUBE_IMAP_USERNAME": data.imap_username,
            "MAILTUBE_IMAP_PASSWORD_FILE": "/run/secrets/imap_password",
            "MAILTUBE_SMTP_HOST": data.smtp_host,
            "MAILTUBE_SMTP_PORT": data.smtp_port,
            "MAILTUBE_SMTP_USERNAME": data.smtp_username,
            "MAILTUBE_SMTP_PASSWORD_FILE": "/run/secrets/smtp_password",
            "MAILTUBE_SMTP_FROM": data.smtp_from,
            "MAILTUBE_SMTP_SECURITY": data.smtp_security,
            "MAILTUBE_SENDER_POLICY": data.sender_policy,
            "MAILTUBE_SENDER_ALLOWLIST": ",".join(data.sender_allowlist),
            "MAILTUBE_DELIVERY_MODE": data.delivery_mode,
            "MAILTUBE_STORAGE_BACKEND": data.storage_backend,
            "MAILTUBE_S3_ENDPOINT": data.s3_endpoint,
            "MAILTUBE_S3_REGION": data.s3_region,
            "MAILTUBE_S3_BUCKET": data.s3_bucket,
            "MAILTUBE_S3_ACCESS_KEY_ID": data.s3_access_key_id,
            "MAILTUBE_S3_SECRET_ACCESS_KEY_FILE": "/run/secrets/s3_secret_access_key",
            "MAILTUBE_S3_FORCE_PATH_STYLE": str(data.s3_force_path_style).lower(),
            "MAILTUBE_MAX_CONCURRENT_JOBS": concurrency,
            "MAILTUBE_MAX_URLS_PER_BATCH": data.max_urls,
            "MAILTUBE_MAX_FILE_MB": data.max_file_mb,
            "MAILTUBE_RETENTION_HOURS": data.retention_hours,
            "MAILTUBE_POT_PROVIDER_URL": "http://pot-provider:4416" if data.pot_provider else "",
            "MAILTUBE_COOKIES_SOURCE": data.cookies_source or "./secrets/empty-cookies.txt",
            "MAILTUBE_COOKIES_FILE": "/run/secrets/youtube-cookies.txt"
            if data.cookies_source
            else "",
            "COMPOSE_PROFILES": ",".join(
                profile
                for profile, enabled in (
                    ("pot-provider", data.pot_provider),
                    ("minio", data.storage_preset == "minio"),
                )
                if enabled
            ),
        }
        env_path = self.config_dir / ".env"
        env_text = (
            "\n".join(f"{key}={json.dumps(str(value))}" for key, value in env_values.items()) + "\n"
        )
        env_path.write_text(env_text, encoding="utf-8")
        env_path.chmod(0o600)
        compose_path = self.config_dir / "compose.yml"
        compose_path.write_text(COMPOSE_TEMPLATE, encoding="utf-8")
        compose_path.chmod(0o600)
        return self.config_dir


COMPOSE_TEMPLATE = """services:
  mailtube:
    image: ${MAILTUBE_IMAGE}
    restart: unless-stopped
    init: true
    env_file: .env
    ports:
      - "${MAILTUBE_BIND_ADDRESS}:${MAILTUBE_HTTP_PORT}:8080"
    volumes:
      - mailtube-data:/data
      - mailtube-work:/work
      - ${MAILTUBE_COOKIES_SOURCE}:/run/secrets/youtube-cookies.txt:ro
    secrets:
      - admin_password_hash
      - session_secret
      - imap_password
      - smtp_password
      - s3_secret_access_key
    read_only: true
    tmpfs:
      - /tmp:size=64m,mode=1777
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

  pot-provider:
    image: brainicism/bgutil-ytdlp-pot-provider:1.3.1-deno
    profiles: ["pot-provider"]
    restart: unless-stopped
    expose: ["4416"]
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true

  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    profiles: ["minio"]
    command: server /data --console-address :9001
    restart: unless-stopped
    environment:
      MINIO_ROOT_USER: ${MAILTUBE_S3_ACCESS_KEY_ID}
      MINIO_ROOT_PASSWORD_FILE: /run/secrets/s3_secret_access_key
    secrets:
      - s3_secret_access_key
    volumes:
      - minio-data:/data
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true

volumes:
  mailtube-data:
  mailtube-work:
  minio-data:

secrets:
  admin_password_hash:
    file: ./secrets/admin_password_hash
  session_secret:
    file: ./secrets/session_secret
  imap_password:
    file: ./secrets/imap_password
  smtp_password:
    file: ./secrets/smtp_password
  s3_secret_access_key:
    file: ./secrets/s3_secret_access_key
"""


def run_setup() -> None:
    config_dir = Path(os.getenv("MAILTUBE_CONFIG_DIR", "./mailtube-config")).resolve()
    result = MailTubeSetupApp(config_dir).run()
    if result:
        print(f"MailTube configuration written to {result}")
