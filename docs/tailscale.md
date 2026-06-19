# Tailscale

Keep Docker bound to `127.0.0.1`. During guided setup, MailTube detects the machine's MagicDNS name and publishes the local listener with Tailscale Serve on a matching HTTPS port. A local listener on `127.0.0.1:36006`, for example, becomes `https://machine.tailnet.ts.net:36006`. HTTPS is required; the equivalent `http://` address is not served.

```bash
tailscale serve --https=36006 --bg --yes http://127.0.0.1:36006
```

This keeps the backend off the LAN and lets Tailscale terminate HTTPS. Set `MAILTUBE_TAILSCALE_HTTPS_PORT` before installation to choose a different HTTPS port. If automatic activation lacks permission, the installer prints the exact `sudo tailscale serve` recovery command.

Add the resulting hostname to `MAILTUBE_ALLOWED_HOSTS`, set `MAILTUBE_PUBLIC_URL` to the HTTPS URL, and enable secure cookies. MailTube retains its own administrator login; Tailscale identity is defense in depth. Do not trust Tailscale identity headers if the backend is exposed on a non-loopback interface.

When Secure cookies are enabled, use the HTTPS Tailscale URL for login and authenticated diagnostics. Local HTTP remains suitable for the unauthenticated liveness check, but browsers will not retain an authenticated MailTube session there.
