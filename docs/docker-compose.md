# Manual Docker Compose

Copy `.env.example` to `.env`, generate a password hash with `docker compose run --rm mailtube mailtube hash-password`, and create a random session secret of at least 32 characters. Set both in `.env`, which must remain mode `0600` and uncommitted.

Run `docker compose config` before `docker compose up -d`. The default binds to `127.0.0.1:8080`, drops all Linux capabilities, sets `no-new-privileges`, uses a read-only root filesystem, and writes only to `/data`, `/work`, and bounded `/tmp`.

Enable optional profiles with `COMPOSE_PROFILES=pot-provider` or `COMPOSE_PROFILES=minio`. Never mount `/var/run/docker.sock` into MailTube.
