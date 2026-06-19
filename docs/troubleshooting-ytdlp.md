# yt-dlp troubleshooting

HTTP 402, 403, 429, “confirm you're not a bot,” and unavailable formats often reflect IP reputation or evolving YouTube checks. First update to a signed current MailTube release. Residential/home-network deployment is usually more reliable than VPS, VPN, or hosting-provider IP space.

The main image includes current yt-dlp, EJS support, ffmpeg, and Deno. The optional bgutil PO-token provider can satisfy some attestation paths but is not a guarantee. Cookies may need to originate from the same external IP; treat them as account credentials and use a dedicated account.

Cookies are optional and are not a general fix for blocked VPS or datacenter IPs. They let yt-dlp reuse an authenticated YouTube browser session when YouTube requires sign-in or presents an account challenge. MailTube intentionally accepts the Netscape cookie file only during the host setup/configuration flow, not through the web dashboard, because the file can grant access to the associated account. Store it with mode `0600`, use a dedicated account, and rotate the account session if the file may have leaked.

Collect a redacted `mailtube doctor` report. Never post video URLs, cookies, sender addresses, credentials, or presigned links in an issue.
