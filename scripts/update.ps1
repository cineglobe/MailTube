param(
  [string]$ConfigDir = $(if ($env:MAILTUBE_CONFIG_DIR) { $env:MAILTUBE_CONFIG_DIR } else { Join-Path $HOME ".config\mailtube" }),
  [string]$ManifestUrl = $env:MAILTUBE_MANIFEST_URL,
  [string]$CosignIdentity = $env:MAILTUBE_COSIGN_IDENTITY
)
$ErrorActionPreference = "Stop"
if (-not $ManifestUrl -or -not $CosignIdentity) { throw "ManifestUrl and CosignIdentity are required." }
if (-not (Get-Command cosign -ErrorAction SilentlyContinue)) { throw "cosign is required." }

$Manifest = Invoke-RestMethod -Uri $ManifestUrl
$Reference = "$($Manifest.image)@$($Manifest.digest)"
$Current = docker compose --env-file "$ConfigDir\.env" -f "$ConfigDir\compose.yml" exec -T mailtube python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health'))['version'])"
if (($Current.Split('.')[0]) -ne (($Manifest.version).Split('.')[0])) { throw "Major updates require explicit operator approval." }
cosign verify $Reference --certificate-identity $CosignIdentity --certificate-oidc-issuer https://token.actions.githubusercontent.com | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Image signature verification failed." }
cosign verify-attestation $Reference --type slsaprovenance --certificate-identity $CosignIdentity --certificate-oidc-issuer https://token.actions.githubusercontent.com | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Image provenance verification failed." }

$EnvPath = "$ConfigDir\.env"
$OldEnv = Get-Content -Raw $EnvPath
docker compose --env-file $EnvPath -f "$ConfigDir\compose.yml" exec -T mailtube mailtube backup "/data/backups/pre-update-$($Manifest.version).db"
docker pull $Reference
($OldEnv -replace '(?m)^MAILTUBE_IMAGE=.*$', "MAILTUBE_IMAGE=$Reference") | Set-Content -NoNewline $EnvPath
docker compose --env-file $EnvPath -f "$ConfigDir\compose.yml" up -d
Start-Sleep -Seconds 15
docker compose --env-file $EnvPath -f "$ConfigDir\compose.yml" exec -T mailtube python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)" | Out-Null
if ($LASTEXITCODE -ne 0) {
  $OldEnv | Set-Content -NoNewline $EnvPath
  docker compose --env-file $EnvPath -f "$ConfigDir\compose.yml" up -d
  throw "Update failed health checks and was rolled back."
}
Write-Host "Updated MailTube to $($Manifest.version)"
