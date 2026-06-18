from email.message import EmailMessage

import pytest

from mailtube.email.parser import message_body, normalize_youtube_url, parse_requests


@pytest.mark.parametrize(
    ("raw", "video_id"),
    [
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_normalizes_supported_urls(raw: str, video_id: str) -> None:
    normalized, actual_id = normalize_youtube_url(raw)
    assert normalized == f"https://www.youtube.com/watch?v={video_id}"
    assert actual_id == video_id


@pytest.mark.parametrize(
    "raw",
    [
        "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
        "https://evil.example/youtube.com/watch?v=dQw4w9WgXcQ",
        "file:///etc/passwd",
        "https://youtube.com/playlist?list=dQw4w9WgXcQ",
        "https://youtu.be/not-valid",
    ],
)
def test_rejects_malicious_or_unsupported_urls(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_youtube_url(raw)


def test_parses_mixed_formats_deduplicates_and_ignores_reply_history() -> None:
    requests, issues = parse_requests(
        """Hello
https://youtu.be/dQw4w9WgXcQ MP4 1080P
https://youtu.be/dQw4w9WgXcQ mp3 320k
https://youtu.be/dQw4w9WgXcQ mp3 320k
On yesterday Someone wrote:
https://youtu.be/9bZkp7q19f0 wav 48khz
"""
    )
    assert not issues
    assert [(item.format, item.quality) for item in requests] == [
        ("mp4", "1080p"),
        ("mp3", "320k"),
    ]


def test_extracts_plain_text_and_ignores_attachments() -> None:
    message = EmailMessage()
    message.set_content("https://youtu.be/dQw4w9WgXcQ mp3")
    message.add_attachment(b"https://youtu.be/9bZkp7q19f0 wav", maintype="text", subtype="plain")
    assert "dQw4w9WgXcQ" in message_body(message)
    assert "9bZkp7q19f0" not in message_body(message)


def test_invalid_quality_is_reported_without_blocking_valid_lines() -> None:
    requests, issues = parse_requests(
        "https://youtu.be/dQw4w9WgXcQ mp3 999k\nhttps://youtu.be/9bZkp7q19f0 mp4 720p"
    )
    assert [request.video_id for request in requests] == ["9bZkp7q19f0"]
    assert issues[0].line == 1
    assert "999k" in issues[0].message
