from __future__ import annotations

import html
import re
from dataclasses import dataclass
from email.message import Message
from urllib.parse import parse_qs, urlparse

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
FORMATS = {"mp4", "mp3", "wav"}
UNSUPPORTED_FORMAT_TOKENS = {"m4a", "webm", "flac", "aac", "mov", "mkv"}
QUALITIES = {
    "mp4": {"360p", "480p", "720p", "1080p", "1440p", "2160p", "best"},
    "mp3": {"128k", "192k", "256k", "320k"},
    "wav": {"44.1khz", "48khz"},
}
DEFAULT_QUALITIES = {"mp4": "720p", "mp3": "192k", "wav": "44.1khz"}


@dataclass(frozen=True)
class ConversionRequest:
    url: str
    video_id: str
    format: str
    quality: str

    def as_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "video_id": self.video_id,
            "format": self.format,
            "quality": self.quality,
        }


@dataclass(frozen=True)
class ParseIssue:
    line: int
    message: str


def normalize_youtube_url(raw: str) -> tuple[str, str]:
    candidate = html.unescape(raw).strip().rstrip(".,);]}")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP(S) YouTube links are accepted")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host == "m.youtube.com":
        host = "youtube.com"
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host == "youtube.com":
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/shorts/", "/live/", "/embed/", "/v/")):
            video_id = parsed.path.strip("/").split("/")[1]
    else:
        raise ValueError("Only youtube.com and youtu.be links are accepted")
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("The link does not contain a valid YouTube video ID")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def strip_quoted_reply(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if re.match(r"^On .+ wrote:$", stripped, re.IGNORECASE):
            break
        if stripped in {"--", "-- "}:
            break
        kept.append(line)
    return "\n".join(kept)


def parse_requests(
    text: str,
    *,
    default_format: str = "mp4",
    defaults: dict[str, str] | None = None,
    max_items: int = 5,
) -> tuple[list[ConversionRequest], list[ParseIssue]]:
    default_quality = {**DEFAULT_QUALITIES, **(defaults or {})}
    requests: list[ConversionRequest] = []
    issues: list[ParseIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for line_number, line in enumerate(strip_quoted_reply(text).splitlines(), start=1):
        match = URL_RE.search(line)
        if not match:
            continue
        if len(requests) >= max_items:
            issues.append(
                ParseIssue(line_number, f"Only {max_items} links are allowed per request")
            )
            break
        try:
            url, video_id = normalize_youtube_url(match.group(0))
        except ValueError as exc:
            issues.append(ParseIssue(line_number, str(exc)))
            continue
        tokens = re.findall(r"[A-Za-z0-9.]+", line[match.end() :].lower())
        unsupported_format = next(
            (token for token in tokens if token in UNSUPPORTED_FORMAT_TOKENS), None
        )
        if unsupported_format:
            issues.append(
                ParseIssue(line_number, f"Unsupported output format: {unsupported_format}")
            )
            continue
        output_format = next((token for token in tokens if token in FORMATS), default_format)
        if output_format not in FORMATS:
            output_format = "mp4"
        quality_token = next(
            (
                token
                for token in tokens
                if re.fullmatch(r"(?:\d+p|\d+k|\d+(?:\.\d+)?khz|best)", token)
            ),
            None,
        )
        if quality_token and quality_token not in QUALITIES[output_format]:
            issues.append(
                ParseIssue(
                    line_number,
                    f"Unsupported {output_format.upper()} quality: {quality_token}",
                )
            )
            continue
        quality = quality_token or default_quality[output_format]
        key = (video_id, output_format, quality)
        if key in seen:
            continue
        seen.add(key)
        requests.append(ConversionRequest(url, video_id, output_format, quality))
    return requests, issues


def message_body(message: Message, *, max_chars: int = 200_000) -> str:
    plain: list[str] = []
    html_parts: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        disposition = (part.get("Content-Disposition") or "").lower()
        if "attachment" in disposition:
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
        if content_type == "text/plain":
            plain.append(decoded)
        else:
            html_parts.append(decoded)
    text = "\n".join(plain)
    if not text and html_parts:
        text = re.sub(r"<[^>]+>", " ", "\n".join(html_parts))
        text = html.unescape(text)
    return text[:max_chars]
