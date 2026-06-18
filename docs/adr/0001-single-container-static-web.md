# ADR 0001: One Python runtime with a static web export

Status: accepted.

MailTube compiles Next.js at image-build time and serves the static export from FastAPI. This removes the resident Node server, proxy boundary, and separate lifecycle while retaining React/shadcn development ergonomics. The consequence is that dashboard routes must remain static-export compatible and all runtime data comes from same-origin client API calls.
