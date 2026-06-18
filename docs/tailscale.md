# Tailscale

Keep Docker bound to `127.0.0.1`, then explicitly run `tailscale serve --bg http://127.0.0.1:8080`. This keeps the backend off the LAN and lets Tailscale terminate HTTPS.

Add the resulting hostname to `MAILTUBE_ALLOWED_HOSTS`, set `MAILTUBE_PUBLIC_URL` to the HTTPS URL, and enable secure cookies. MailTube retains its own administrator login; Tailscale identity is defense in depth. Do not trust Tailscale identity headers if the backend is exposed on a non-loopback interface.
