param(
  [string]$ConfigDir = $(if ($env:MAILTUBE_CONFIG_DIR) { $env:MAILTUBE_CONFIG_DIR } else { Join-Path $HOME ".config\mailtube" }),
  [string]$ManifestUrl = $(if ($env:MAILTUBE_MANIFEST_URL) { $env:MAILTUBE_MANIFEST_URL } else { "https://github.com/cineglobe/MailTube/releases/latest/download/stable-manifest.json" }),
  [string]$CosignIdentity = $(if ($env:MAILTUBE_COSIGN_IDENTITY) { $env:MAILTUBE_COSIGN_IDENTITY } else { "https://github.com/cineglobe/MailTube/.github/workflows/release.yml@refs/heads/main" })
)
$ErrorActionPreference = "Stop"
$EnvPath = "$ConfigDir\.env"
$ComposePath = "$ConfigDir\compose.yml"
$LockPath = "$ConfigDir\.update.lock"

try {
  New-Item -ItemType Directory -Path $LockPath -ErrorAction Stop | Out-Null
} catch {
  Write-Host "A MailTube update check is already running"
  exit 0
}

try {
  $Channel = docker compose --env-file $EnvPath -f $ComposePath exec -T mailtube python -c 'from mailtube.config import Settings; from mailtube.db import Database; s=Settings(); print(Database(s.db_path).get_runtime_settings().get("update_channel", s.update_channel))'
  if ($Channel.Trim() -ne "stable") {
    Write-Host "MailTube stable updates are disabled"
    exit 0
  }

  $Manifest = Invoke-RestMethod -Uri $ManifestUrl
  if ($Manifest.version -notmatch '^\d+\.\d+\.\d+$' -or $Manifest.digest -notmatch '^sha256:[0-9a-f]{64}$') {
    throw "Stable manifest contains an invalid version or digest"
  }
  if ($Manifest.image -ne "ghcr.io/cineglobe/mailtube") { throw "Stable manifest contains an unexpected image" }
  $Reference = "$($Manifest.image)@$($Manifest.digest)"
  $Current = (docker compose --env-file $EnvPath -f $ComposePath exec -T mailtube python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health'))['version'])").Trim()
  $CurrentVersion = [version]$Current
  $TargetVersion = [version]$Manifest.version
  if ($TargetVersion -eq $CurrentVersion) {
    Write-Host "MailTube $Current is already current"
    exit 0
  }
  if ($TargetVersion -lt $CurrentVersion) { throw "Refusing to downgrade MailTube $Current to $($Manifest.version)" }
  if ($CurrentVersion.Major -ne $TargetVersion.Major) { throw "Major updates require explicit operator approval" }

  $OldImage = (((Get-Content $EnvPath | Where-Object { $_ -like 'MAILTUBE_IMAGE=*' }) -replace '^MAILTUBE_IMAGE=', '').Trim('"'))
  $CosignArgs = @("verify", $Reference, "--certificate-identity", $CosignIdentity, "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com")
  if (Get-Command cosign -ErrorAction SilentlyContinue) {
    & cosign @CosignArgs | Out-Null
    & cosign verify-attestation $Reference --type slsaprovenance --certificate-identity $CosignIdentity --certificate-oidc-issuer https://token.actions.githubusercontent.com | Out-Null
  } else {
    docker run --rm -e HOME=/tmp --entrypoint /usr/local/bin/cosign $OldImage @CosignArgs | Out-Null
    docker run --rm -e HOME=/tmp --entrypoint /usr/local/bin/cosign $OldImage verify-attestation $Reference --type slsaprovenance --certificate-identity $CosignIdentity --certificate-oidc-issuer https://token.actions.githubusercontent.com | Out-Null
  }

  $BackupPath = "/data/backups/pre-update-$($Manifest.version).db"
  docker compose --env-file $EnvPath -f $ComposePath exec -T mailtube mailtube backup $BackupPath
  $OldEnv = Get-Content -Raw $EnvPath
  $OldCompose = Get-Content -Raw $ComposePath
  docker pull $Reference
  ($OldEnv -replace '(?m)^MAILTUBE_IMAGE=.*$', "MAILTUBE_IMAGE=$Reference") | Set-Content -NoNewline $EnvPath
  docker run --rm -e MAILTUBE_CONFIG_DIR=/config -e MAILTUBE_IMAGE=$Reference -v "${ConfigDir}:/config" $Reference mailtube refresh-compose
  docker compose --env-file $EnvPath -f $ComposePath up -d

  $Healthy = $false
  for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    docker compose --env-file $EnvPath -f $ComposePath exec -T mailtube python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $Healthy = $true; break }
    Start-Sleep -Seconds 2
  }
  if (-not $Healthy) {
    $OldEnv | Set-Content -NoNewline $EnvPath
    $OldCompose | Set-Content -NoNewline $ComposePath
    docker compose --env-file $EnvPath -f $ComposePath stop mailtube
    docker compose --env-file $EnvPath -f $ComposePath run --rm --no-deps -e BACKUP_PATH=$BackupPath --entrypoint /bin/sh mailtube -ec 'cp "$BACKUP_PATH" /data/mailtube.db; rm -f /data/mailtube.db-wal /data/mailtube.db-shm'
    docker compose --env-file $EnvPath -f $ComposePath up -d
    throw "Update failed health checks; restored MailTube $Current and its database"
  }
  Write-Host "Updated MailTube $Current -> $($Manifest.version)"
} finally {
  Remove-Item -Recurse -Force $LockPath -ErrorAction SilentlyContinue
}
