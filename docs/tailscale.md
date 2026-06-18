# Tailscale

Keep Docker bound to `127.0.0.1`. MailTube does not modify Tailscale Serve automatically because an implicit root route could replace an existing service. Inspect current routes with `tailscale serve status`, choose an unused HTTPS port, then publish MailTube explicitly:

```bash
tailscale serve --https=19179 --bg http://127.0.0.1:8080
```

This keeps the backend off the LAN and lets Tailscale terminate HTTPS. Change `19179` and `8080` to the ports you selected.

Add the resulting hostname to `MAILTUBE_ALLOWED_HOSTS`, set `MAILTUBE_PUBLIC_URL` to the HTTPS URL, and enable secure cookies. MailTube retains its own administrator login; Tailscale identity is defense in depth. Do not trust Tailscale identity headers if the backend is exposed on a non-loopback interface.

When Secure cookies are enabled, use the HTTPS Tailscale URL for login and authenticated diagnostics. Local HTTP remains suitable for the unauthenticated liveness check, but browsers will not retain an authenticated MailTube session there.
