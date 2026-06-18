# Cloudflare R2

Create a private bucket and a dedicated API token limited to that bucket. In setup choose R2/generic S3, use the account endpoint `https://ACCOUNT_ID.r2.cloudflarestorage.com`, region `auto`, and enter the access key, secret, and bucket.

The wizard writes, reads, presigns, and deletes a random test object. Presigned URLs are bearer credentials: anyone with the URL can download until expiry. Do not log or forward them. Configure a provider lifecycle rule slightly longer than MailTube retention as defense in depth.
