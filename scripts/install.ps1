$ErrorActionPreference = "Stop"
$Image = if ($env:MAILTUBE_IMAGE) { $env:MAILTUBE_IMAGE } else { "ghcr.io/cineglobe/mailtube:latest" }
$ConfigDir = if ($env:MAILTUBE_CONFIG_DIR) { $env:MAILTUBE_CONFIG_DIR } else { Join-Path $HOME ".config\mailtube" }
$SetupFile = $env:MAILTUBE_SETUP_FILE

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker Desktop is required." }
docker compose version | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
docker pull $Image
$Digest = docker image inspect $Image --format '{{index .RepoDigests 0}}'
if (-not $Digest) { throw "Could not resolve an immutable image digest." }
if ($SetupFile) {
  if (-not (Test-Path -PathType Leaf $SetupFile)) { throw "MAILTUBE_SETUP_FILE does not exist: $SetupFile" }
  Get-Content -Raw $SetupFile | docker run --rm -i -e MAILTUBE_CONFIG_DIR=/config -e MAILTUBE_IMAGE=$Digest -v "${ConfigDir}:/config" $Digest mailtube setup --non-interactive -
} else {
  docker run --rm -it -e MAILTUBE_CONFIG_DIR=/config -e MAILTUBE_IMAGE=$Digest -v "${ConfigDir}:/config" $Digest mailtube setup
}
docker compose --env-file "$ConfigDir\.env" -f "$ConfigDir\compose.yml" config | Out-Null
docker compose --env-file "$ConfigDir\.env" -f "$ConfigDir\compose.yml" run --rm --no-deps secrets-init
if ($LASTEXITCODE -ne 0) { throw "Could not initialize the private secrets volume." }
docker compose --env-file "$ConfigDir\.env" -f "$ConfigDir\compose.yml" run --rm --no-deps --entrypoint /bin/sh mailtube -ec 'test -r /run/secrets/admin_password_hash -a -r /run/secrets/session_secret'
if ($LASTEXITCODE -ne 0) { throw "Generated secrets are not readable by the non-root MailTube container." }
docker compose --env-file "$ConfigDir\.env" -f "$ConfigDir\compose.yml" up -d
$Healthy = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
  docker compose --env-file "$ConfigDir\.env" -f "$ConfigDir\compose.yml" exec -T mailtube python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)" 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $Healthy = $true
    break
  }
  Start-Sleep -Seconds 2
}
if (-not $Healthy) { throw "MailTube did not become healthy. Inspect the Compose logs." }

$PublicUrl = ((Get-Content "$ConfigDir\.env" | Where-Object { $_ -like 'MAILTUBE_PUBLIC_URL=*' }) -replace '^MAILTUBE_PUBLIC_URL=', '').Trim('"')
if ($PublicUrl -like 'https://*') {
  Write-Host "Secure cookies are enabled. Use $PublicUrl for login and diagnostics; local HTTP sessions will not retain authentication."
}

if ($env:MAILTUBE_MANIFEST_URL -and $env:MAILTUBE_COSIGN_IDENTITY) {
  $UpdaterContainer = docker create $Digest
  docker cp "${UpdaterContainer}:/usr/local/share/mailtube/update.ps1" "$ConfigDir\update.ps1"
  docker rm $UpdaterContainer | Out-Null
  $Arguments = "-NoProfile -File `"$ConfigDir\update.ps1`" -ConfigDir `"$ConfigDir`" -ManifestUrl `"$env:MAILTUBE_MANIFEST_URL`" -CosignIdentity `"$env:MAILTUBE_COSIGN_IDENTITY`""
  $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Arguments
  $Trigger = New-ScheduledTaskTrigger -Daily -At 3am
  Register-ScheduledTask -TaskName "MailTube Stable Update" -Action $Action -Trigger $Trigger -Force | Out-Null
}
$DashboardUrl = if ($PublicUrl) { $PublicUrl } else { "http://127.0.0.1:8080" }
Write-Host "MailTube is ready at $DashboardUrl"
