# MinIO

The optional `minio` Compose profile is suitable for a private local deployment, but it is not an off-site backup. Set a strong `MINIO_ROOT_PASSWORD`, start the profile, create a private bucket, and configure MailTube with endpoint `http://minio:9000`, region `us-east-1`, and path-style access.

The console and API publish to localhost by default. Do not expose them publicly. Use restricted application credentials after initial bootstrap.
