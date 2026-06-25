from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from mailtube.email.templates import (
    DEFAULT_ERROR_EMAIL_TEMPLATE_HTML,
    DEFAULT_RESULT_EMAIL_TEMPLATE_HTML,
)


def validate_mail_host(value: str) -> str:
    """Validate a mail server host without accepting a URL or embedded port."""
    value = value.strip()
    if not value:
        raise ValueError("mail host must not be empty")
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if (
        "://" in value
        or ":" in value
        or "/" in value
        or any(character.isspace() for character in value)
    ):
        raise ValueError("mail host must be a hostname only; enter the port separately")
    hostname = value.rstrip(".")
    if len(hostname) > 253 or not all(
        label
        and len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in hostname.split(".")
    ):
        raise ValueError("mail host is not a valid hostname")
    return hostname.lower()


class Settings(BaseSettings):
    """Validated runtime settings. Every environment key is prefixed MAILTUBE_."""

    model_config = SettingsConfigDict(
        env_prefix="MAILTUBE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["production", "development", "test"] = "production"
    host: str = "0.0.0.0"  # noqa: S104 - container bind, host publishing controls exposure
    port: int = 8080
    public_url: str = "http://127.0.0.1:8080"
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )
    secure_cookies: bool = False

    data_dir: Path = Path("/data")
    work_dir: Path = Path("/work")
    static_dir: Path = Path("/app/static")
    database_path: Path | None = None

    admin_username: str = "admin"
    admin_password_hash: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    session_hours: int = 24

    max_urls_per_batch: int = 5
    max_concurrent_jobs: int = 1
    max_duration_seconds: int = 7200
    max_file_mb: int = 1024
    job_timeout_seconds: int = 7200
    inactivity_timeout_seconds: int = 300
    retention_hours: int = 24
    cleanup_interval_seconds: int = 900
    default_format: Literal["mp4", "mp3", "wav"] = "mp4"
    default_mp4_quality: str = "720p"
    default_mp3_quality: str = "192k"
    default_wav_quality: str = "44.1khz"
    cookies_file: Path | None = None
    pot_provider_url: str | None = None

    email_enabled: bool = False
    poll_interval_seconds: int = 15
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_folder: str = "INBOX"
    imap_username: str = ""
    imap_password: SecretStr = SecretStr("")
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_security: Literal["starttls", "tls"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_from_name: str = "MailTube"
    sender_policy: Literal["allowlist", "any"] = "allowlist"
    sender_allowlist: Annotated[list[str], NoDecode] = Field(default_factory=list)
    delivery_mode: Literal["links", "hybrid", "attachments"] = "links"
    max_attachment_mb: int = 18
    email_success_template_html: str = Field(
        default=DEFAULT_RESULT_EMAIL_TEMPLATE_HTML, max_length=30000
    )
    email_partial_template_html: str = Field(
        default=DEFAULT_RESULT_EMAIL_TEMPLATE_HTML, max_length=30000
    )
    email_failure_template_html: str = Field(
        default=DEFAULT_RESULT_EMAIL_TEMPLATE_HTML, max_length=30000
    )
    email_error_template_html: str = Field(
        default=DEFAULT_ERROR_EMAIL_TEMPLATE_HTML, max_length=30000
    )

    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint: str | None = None
    s3_region: str = "auto"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_force_path_style: bool = False

    update_channel: Literal["stable", "off"] = "stable"
    instance_id: str = "default"
    max_email_requests_per_hour: int = 10

    def __init__(self, **values: Any) -> None:
        secret_fields = (
            "admin_password_hash",
            "session_secret",
            "imap_password",
            "smtp_password",
            "s3_secret_access_key",
        )
        for field_name in secret_fields:
            if field_name in values:
                continue
            file_value = os.getenv(f"MAILTUBE_{field_name.upper()}_FILE")
            if file_value:
                values[field_name] = Path(file_value).read_text(encoding="utf-8").rstrip("\r\n")
        super().__init__(**values)

    @field_validator("allowed_hosts", "sender_allowlist", mode="before")
    @classmethod
    def parse_list(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("imap_host", "smtp_host")
    @classmethod
    def validate_email_hostname(cls, value: str) -> str:
        return validate_mail_host(value)

    @field_validator("cookies_file", mode="before")
    @classmethod
    def empty_cookies_path_is_unconfigured(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("instance_id")
    @classmethod
    def validate_instance_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value):
            raise ValueError(
                "instance_id must contain only letters, numbers, underscores, or hyphens"
            )
        return value

    @property
    def db_path(self) -> Path:
        return self.database_path or self.data_dir / "mailtube.db"

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024

    def prepare_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def validate_runtime_secrets(self) -> None:
        if self.environment == "test":
            return
        if not self.admin_password_hash.get_secret_value():
            raise ValueError("MAILTUBE_ADMIN_PASSWORD_HASH is required; run `mailtube setup`")
        if len(self.session_secret.get_secret_value()) < 32:
            raise ValueError("MAILTUBE_SESSION_SECRET must contain at least 32 characters")
        if self.email_enabled and not self.imap_password.get_secret_value():
            raise ValueError("Email is enabled but MAILTUBE_IMAP_PASSWORD is empty")
        if self.email_enabled and not self.smtp_password.get_secret_value():
            raise ValueError("Email is enabled but MAILTUBE_SMTP_PASSWORD is empty")
        if self.email_enabled and self.delivery_mode in {"links", "hybrid"}:
            if self.storage_backend != "s3":
                raise ValueError("Link and hybrid email delivery require S3-compatible storage")
