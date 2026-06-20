from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from mailtube.email.parser import QUALITIES, normalize_youtube_url


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class JobItemRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    format: Literal["mp4", "mp3", "wav"] = "mp4"
    quality: str = "720p"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized, _ = normalize_youtube_url(value)
        return normalized

    @field_validator("quality")
    @classmethod
    def normalize_quality(cls, value: str) -> str:
        return value.lower()

    def validated_dict(self) -> dict[str, str]:
        normalized, video_id = normalize_youtube_url(self.url)
        if self.quality not in QUALITIES[self.format]:
            raise ValueError(f"Unsupported {self.format} quality: {self.quality}")
        return {
            "url": normalized,
            "video_id": video_id,
            "format": self.format,
            "quality": self.quality,
        }


class CreateJobsRequest(BaseModel):
    items: list[JobItemRequest] = Field(min_length=1, max_length=25)


class RuntimeSettingsUpdate(BaseModel):
    admin_username: str | None = Field(default=None, min_length=1, max_length=128)
    admin_password: str | None = Field(default=None, min_length=12, max_length=1024)
    sender_policy: Literal["allowlist", "any"] | None = None
    sender_allowlist: list[str] | None = None
    retention_hours: int | None = Field(default=None, ge=1, le=168)
    max_urls_per_batch: int | None = Field(default=None, ge=1, le=25)
    max_concurrent_jobs: int | None = Field(default=None, ge=1, le=8)
    max_duration_seconds: int | None = Field(default=None, ge=60, le=86400)
    max_file_mb: int | None = Field(default=None, ge=25, le=10240)
    job_timeout_seconds: int | None = Field(default=None, ge=60, le=86400)
    inactivity_timeout_seconds: int | None = Field(default=None, ge=30, le=3600)
    default_format: Literal["mp4", "mp3", "wav"] | None = None
    default_mp4_quality: str | None = None
    default_mp3_quality: str | None = None
    default_wav_quality: str | None = None
    email_enabled: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    imap_host: str | None = Field(default=None, min_length=1, max_length=253)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    imap_folder: str | None = Field(default=None, min_length=1, max_length=255)
    imap_username: str | None = Field(default=None, max_length=320)
    imap_password: str | None = Field(default=None, min_length=1, max_length=1024)
    smtp_host: str | None = Field(default=None, min_length=1, max_length=253)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: Literal["starttls", "tls"] | None = None
    smtp_username: str | None = Field(default=None, max_length=320)
    smtp_password: str | None = Field(default=None, min_length=1, max_length=1024)
    smtp_from: str | None = Field(default=None, max_length=320)
    smtp_from_name: str | None = Field(default=None, max_length=128)
    delivery_mode: Literal["links", "hybrid", "attachments"] | None = None
    max_attachment_mb: int | None = Field(default=None, ge=1, le=24)
    max_email_requests_per_hour: int | None = Field(default=None, ge=1, le=1000)
    storage_backend: Literal["local", "s3"] | None = None
    s3_endpoint: str | None = Field(default=None, max_length=2048)
    s3_region: str | None = Field(default=None, min_length=1, max_length=128)
    s3_bucket: str | None = Field(default=None, max_length=255)
    s3_access_key_id: str | None = Field(default=None, max_length=1024)
    s3_secret_access_key: str | None = Field(default=None, min_length=1, max_length=2048)
    s3_force_path_style: bool | None = None
    pot_provider_url: str | None = Field(default=None, max_length=2048)
    update_channel: Literal["stable", "off"] | None = None
