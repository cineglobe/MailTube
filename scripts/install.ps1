$ErrorActionPreference = "Stop"
$Image = if ($env:MAILTUBE_IMAGE) { $env:MAILTUBE_IMAGE } else { "ghcr.io/OWNER/MailTube:latest" }
$ConfigDir = if ($env:MAILTUBE_CONFIG_DIR) { $env:MAILTUBE_CONFIG_DIR } else { Join-Path $HOME ".config\mailtube" }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker Desktop is required." }
docker compose version | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
docker pull $Image
$Digest = docker image inspect $Image --format '{{index .RepoDigests 0}}'
if (-not $Digest) { throw "Could not resolve an immutable image digest." }
docker run --rm -it -e MAILTUBE_CONFIG_DIR=/config -e MAILTUBE_IMAGE=$Digest -v "${ConfigDir}:/config" $Digest mailtube setup
docker compose --env-file "$ConfigDir\.env" -f "$ConfigDir\compose.yml" config | Out-Null
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

if ($env:MAILTUBE_MANIFEST_URL -and $env:MAILTUBE_COSIGN_IDENTITY) {
  $UpdaterContainer = docker create $Digest
  docker cp "${UpdaterContainer}:/usr/local/share/mailtube/update.ps1" "$ConfigDir\update.ps1"
  docker rm $UpdaterContainer | Out-Null
  $Arguments = "-NoProfile -File `"$ConfigDir\update.ps1`" -ConfigDir `"$ConfigDir`" -ManifestUrl `"$env:MAILTUBE_MANIFEST_URL`" -CosignIdentity `"$env:MAILTUBE_COSIGN_IDENTITY`""
  $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Arguments
  $Trigger = New-ScheduledTaskTrigger -Daily -At 3am
  Register-ScheduledTask -TaskName "MailTube Stable Update" -Action $Action -Trigger $Trigger -Force | Out-Null
}
Write-Host "MailTube is ready at http://127.0.0.1:8080"
