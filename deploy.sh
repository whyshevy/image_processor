#!/usr/bin/env bash
# ============================================================
#  deploy.sh — One-command deploy to Synology NAS via Git + SSH
# ============================================================
#
#  Usage:
#    bash deploy.sh
#
#  Flow:
#    1. git push  →  GitHub (from this PC)
#    2. ssh       →  Synology: git clone/pull + docker build & restart
#
#  Prerequisites:
#    - Git installed on this PC and on Synology (via Package Center or opkg)
#    - SSH access to Synology (enable in Control Panel → Terminal & SNMP)
#    - SSH key authentication configured (ssh-copy-id) — recommended
#    - GitHub repo created and remote "origin" set in this project
#    - Docker / Container Manager installed on Synology
# ============================================================

set -euo pipefail

# ── Configuration ───────────────────────────────────────────
SYNOLOGY_USER="Admin_1"                          # SSH user on Synology
SYNOLOGY_HOST="100.119.20.23"                  # Synology IP (Tailscale or LAN)
SYNOLOGY_PORT=22                               # SSH port

REMOTE_DIR="/volume1/docker/image_processor"   # Path on Synology
GIT_BRANCH="main"                              # Branch to deploy
COMPOSE_FILE="docker-compose.synology.yml"

# GitHub repo URL (HTTPS or SSH)
# Example: https://github.com/youruser/image_processor.git
# Example: git@github.com:youruser/image_processor.git
GIT_REPO=""  # ← fill this in or pass as $1
# ────────────────────────────────────────────────────────────

# Override GIT_REPO from CLI argument if provided
if [[ -n "${1:-}" ]]; then
    GIT_REPO="$1"
fi

# Auto-detect repo URL from git remote if not set
if [[ -z "$GIT_REPO" ]]; then
    GIT_REPO=$(git remote get-url origin 2>/dev/null || true)
fi

if [[ -z "$GIT_REPO" ]]; then
    echo "ERROR: GIT_REPO is empty. Set it in the script or pass as argument."
    echo "Usage: bash deploy.sh https://github.com/youruser/image_processor.git"
    exit 1
fi

echo "============================================"
echo "  Deploying to Synology NAS"
echo "============================================"
echo "  Repo:     $GIT_REPO"
echo "  Branch:   $GIT_BRANCH"
echo "  Target:   $SYNOLOGY_USER@$SYNOLOGY_HOST:$REMOTE_DIR"
echo "============================================"
echo ""

# ── Step 1: Push to GitHub ──────────────────────────────────
echo "[1/3] Pushing to GitHub..."
git add -A
git diff --cached --quiet && echo "  (nothing new to commit)" || git commit -m "deploy: $(date '+%Y-%m-%d %H:%M:%S')"
git push origin "$GIT_BRANCH"
echo "  ✓ Pushed to $GIT_BRANCH"
echo ""

# ── Step 2+3: SSH to Synology → clone/pull + docker build ──
echo "[2/3] Connecting to Synology via SSH..."
echo "[3/3] Clone/pull + Docker build..."

ssh -p "$SYNOLOGY_PORT" "${SYNOLOGY_USER}@${SYNOLOGY_HOST}" bash -s <<REMOTE_SCRIPT
set -euo pipefail

echo "  → Connected to Synology"

# Clone or pull
if [ -d "${REMOTE_DIR}/.git" ]; then
    echo "  → Pulling latest changes..."
    cd "${REMOTE_DIR}"
    git fetch origin
    git reset --hard "origin/${GIT_BRANCH}"
    git clean -fd
else
    echo "  → Cloning repository..."
    mkdir -p "\$(dirname ${REMOTE_DIR})"
    git clone --branch "${GIT_BRANCH}" "${GIT_REPO}" "${REMOTE_DIR}"
    cd "${REMOTE_DIR}"
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "  ⚠ .env not found — creating from template..."
    cat > .env <<'ENV_TEMPLATE'
# OpenAI
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4.1

# Flask
FLASK_ENV=production
SECRET_KEY=change-me-to-random-string

# MS SQL Server
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=100.119.20.23,1433
DB_NAME=ProcessedMedia
DB_USER=SA
DB_PASSWORD=your-password-here

# Synology mode
MEDIA_ROOT=/media
ENV_TEMPLATE
    echo "  ⚠ IMPORTANT: Edit .env on Synology before first run!"
    echo "     nano ${REMOTE_DIR}/.env"
fi

# Docker build & restart
echo "  → Building Docker image..."
docker-compose -f "${COMPOSE_FILE}" build

echo "  → Restarting container..."
docker-compose -f "${COMPOSE_FILE}" down 2>/dev/null || true
docker-compose -f "${COMPOSE_FILE}" up -d

echo ""
echo "  ✓ Deployment complete!"
echo "  ✓ App available at: http://${SYNOLOGY_HOST}:5050"
REMOTE_SCRIPT

echo ""
echo "============================================"
echo "  ✓ DONE! App deployed to Synology."
echo "  Open: http://${SYNOLOGY_HOST}:5050"
echo "============================================"
