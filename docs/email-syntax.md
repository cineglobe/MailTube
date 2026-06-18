# Email syntax

Each non-quoted line may contain one normalized `youtube.com` or `youtu.be` video URL followed by optional case-insensitive format and quality tokens.

```text
URL mp4 720p
URL mp3 192k
URL wav 44.1khz
URL
```

Ordinary prose, signatures, quoted replies, HTML noise, and attachments are ignored. Bare URLs use defaults. Exact duplicates collapse; the same video requested in different formats remains separate. Invalid request lines are reported without preventing valid lines from running. Playlists and lookalike hostnames are rejected.
