# Amazon S3

Create a private bucket and a dedicated IAM principal limited to object read/write/delete within the MailTube prefix. Select AWS S3, leave the endpoint unset, choose the bucket region, and test from the wizard.

Block public access, disable ACL-based public delivery, and use short-lived presigned GET requests. MailTube streams multipart uploads from disk and deletes objects at expiry. Add an S3 lifecycle rule as a secondary safeguard.
