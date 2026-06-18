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
    sender_policy: Literal["allowlist", "any"] | None = None
    sender_allowlist: list[str] | None = None
    retention_hours: int | None = Field(default=None, ge=1, le=168)
    max_urls_per_batch: int | None = Field(default=None, ge=1, le=25)
    max_concurrent_jobs: int | None = Field(default=None, ge=1, le=8)
