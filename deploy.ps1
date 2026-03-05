# ============================================================
#  deploy.ps1 — One-command deploy to Synology NAS via Git + SSH
# ============================================================
#
#  Usage (from project root):
#    .\deploy.ps1
#    .\deploy.ps1 -GitRepo "https://github.com/youruser/image_processor.git"
#
#  Flow:
#    1. git push  →  GitHub (from this PC)
#    2. ssh       →  Synology: git clone/pull + docker build & restart
# ============================================================

param(
    [string]$GitRepo = "https://github.com/whyshevy/image_processor.git",
    [string]$SynologyUser = "Admin_1",
    [string]$SynologyHost = "100.119.20.23",
    [int]$SynologyPort = 22,
    [string]$RemoteDir = "/volume1/docker/image_processor",
    [string]$GitBranch = "main",
    [string]$ComposeFile = "docker-compose.synology.yml"
)

$ErrorActionPreference = "Stop"

# Auto-detect repo URL from git remote if not provided
if (-not $GitRepo) {
    $GitRepo = git remote get-url origin 2>$null
}
if (-not $GitRepo) {
    Write-Host "ERROR: Git repo URL not found." -ForegroundColor Red
    Write-Host "Usage: .\deploy.ps1 -GitRepo 'https://github.com/youruser/image_processor.git'"
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Deploying to Synology NAS" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Repo:     $GitRepo"
Write-Host "  Branch:   $GitBranch"
Write-Host "  Target:   ${SynologyUser}@${SynologyHost}:${RemoteDir}"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Push to GitHub ──────────────────────────────────
Write-Host "[1/3] Pushing to GitHub..." -ForegroundColor Yellow
git add -A
$hasChanges = git diff --cached --quiet 2>$null; $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git commit -m "deploy: $ts"
} else {
    Write-Host "  (nothing new to commit)"
}
git push origin $GitBranch
Write-Host "  + Pushed to $GitBranch" -ForegroundColor Green
Write-Host ""

# ── Step 2+3: SSH to Synology ──────────────────────────────
Write-Host "[2/3] Connecting to Synology via SSH..." -ForegroundColor Yellow
Write-Host "[3/3] Clone/pull + Docker build..." -ForegroundColor Yellow

$remoteScript = @"
set -euo pipefail
echo '  -> Connected to Synology'

if [ -d "${RemoteDir}/.git" ]; then
    echo '  -> Pulling latest changes...'
    cd "${RemoteDir}"
    git fetch origin
    git reset --hard "origin/${GitBranch}"
    git clean -fd
else
    echo '  -> Cloning repository...'
    mkdir -p "`$(dirname ${RemoteDir})"
    git clone --branch "${GitBranch}" "${GitRepo}" "${RemoteDir}"
    cd "${RemoteDir}"
fi

if [ ! -f .env ]; then
    echo '  ! .env not found - creating template...'
    cat > .env <<'ENVEOF'
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4.1
FLASK_ENV=production
SECRET_KEY=change-me-to-random-string
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=100.119.20.23,1433
DB_NAME=ProcessedMedia
DB_USER=SA
DB_PASSWORD=your-password-here
MEDIA_ROOT=/media
ENVEOF
    echo '  ! IMPORTANT: edit .env on Synology: nano ${RemoteDir}/.env'
fi

echo '  -> Building Docker image...'
docker-compose -f "${ComposeFile}" build

echo '  -> Restarting container...'
docker-compose -f "${ComposeFile}" down 2>/dev/null || true
docker-compose -f "${ComposeFile}" up -d

echo ''
echo '  + Deployment complete!'
echo '  + App: http://${SynologyHost}:5050'
"@

$remoteScript | ssh -p $SynologyPort "${SynologyUser}@${SynologyHost}" "bash -s"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  + DONE! App deployed to Synology." -ForegroundColor Green
Write-Host "  Open: http://${SynologyHost}:5050" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
