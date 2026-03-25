# Deployment to Synology NAS via GitHub and SSH

## Scheme Overview

```
     PC                Git repo (GitHub)              Synology NAS
  ┌──────┐   1. push    ┌──────────────┐   3. clone   ┌──────────────┐
  │      │ ──────────►  │              │ ◄──────────  │              │
  │  PC  │              │   GitHub     │              │   Synology   │
  │      │ ──────────────────────────────────────────►│              │
  └──────┘   2. ssh (trigger deploy)                  └──────┬───────┘
                                                             │ docker
                                                             ▼
                                                    ┌──────────────┐
                                                    │  Container   │
                                                    │  build+run   │
                                                    └──────────────┘
```

- **Step 1:** You commit and push from your PC to GitHub.
- **Step 2:** You trigger deployment via SSH (using PuTTY or another SSH client).
- **Step 3:** The Synology connects to GitHub, updates code, and builds/runs the Docker container.

---

## Quick Deploy (Single Command)

After initial setup (see below), deployment is performed with a single command:

```powershell
# Windows (PowerShell)
.\deploy.ps1

# or with explicit repo
.\deploy.ps1 -GitRepo "https://github.com/youruser/image_processor.git"
```

```bash
# Linux / macOS / Git Bash
bash deploy.sh
```

The script will automatically:
1. Commit and push changes to GitHub.
2. Connect via SSH to Synology.
3. Clone (or update) the repository on Synology.
4. Build the Docker image.
5. Restart the container.

---

## Requirements

- **Synology NAS** with Intel/AMD (x86-64) CPU. **ARM models are not supported** (ODBC Driver 17 is x86-64 only).
- **Container Manager** (formerly Docker) installed via Package Center.
- **Git** installed on Synology (via Package Center or Entware).
- **Tailscale** installed on Synology and connected to the same network as your SQL Server.
- **SSH** access enabled on Synology (Control Panel → Terminal & SNMP).

---

## Initial Setup

### Step 0. Create a GitHub Repository

1. Create a **private** repository on GitHub (e.g., `image_processor`).
2. On your PC, in the project folder:

```powershell
cd C:\Users\YourName\Desktop\image_processor
git init
git remote add origin https://github.com/YOURUSER/image_processor.git
git add -A
git commit -m "initial commit"
git branch -M main
git push -u origin main
```

### Step 1. Set Up SSH Access to Synology

1. Enable SSH on Synology: **Control Panel → Terminal & SNMP → Enable SSH**
2. On your PC, generate an SSH key (if you don't have one):

```powershell
ssh-keygen -t ed25519
```

3. Copy the public key to Synology:

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh your-synology-user@<SYNOLOGY_IP> "mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys"
```

4. Test the connection (should not prompt for password):

```powershell
ssh your-synology-user@<SYNOLOGY_IP> "echo OK"
```

### Step 2. Install Git on Synology

Connect via SSH and install Git:

```bash
# Via Package Center (recommended):
# Install "Git" or "Git Server" using Package Center UI.

# Or via opkg (if Entware is installed):
sudo opkg install git
```

Verify:
```bash
git --version
```

### Step 3. Configure deploy.ps1

Open `deploy.ps1` and ensure parameters are set correctly:

```powershell
$SynologyUser = "your-synology-user"  # Your Synology SSH user
$SynologyHost = "<SYNOLOGY_IP>"       # Synology's IP (Tailscale or LAN)
$RemoteDir = "/volume1/docker/image_processor"
```

### Step 4. First Deployment

```powershell
.\deploy.ps1
```

After the first deploy, edit the `.env` file on Synology:

```bash
ssh your-synology-user@<SYNOLOGY_IP>
nano /volume1/docker/image_processor/.env
```

Fill in your real values (API keys, secrets, etc.).

> **Note:** Set `MEDIA_ROOT=/media` to enable Synology "media mode" (folder browser in web UI).

---

## Configure Volume Mounts

Edit `docker-compose.synology.yml` and define your Synology shared folders:

```yaml
volumes:
  - ./data/uploads:/app/uploads
  - ./data/processed:/app/processed
  # Mount Synology shared folders into the container at /media/
  - /volume1/photo:/media/photo:ro
  - /volume1/homes/your-synology-user/Photos:/media/my-photos:ro
  # Add as many as needed
```

Each photo folder you want to process must be mounted under `/media/`.

---

## Updating (Daily Workflow)

After making any code changes on your PC:

```powershell
.\deploy.ps1
```

That's it! The script will push, connect to Synology, update the code, and restart the container automatically.

---

## Tailscale: Access to SQL Server

### Option A — `network_mode: host` (Recommended)
The container uses Synology's network stack, including Tailscale. Just specify the Tailscale IP in `DB_SERVER`.

### Option B — Bridge Network
1. In `docker-compose.synology.yml`, comment out `network_mode: host`.
2. Uncomment the `ports` and `extra_hosts` sections.
3. Make sure Tailscale routing allows the container to access SQL Server.

---

## Useful Commands

```bash
# SSH into Synology
ssh your-synology-user@<SYNOLOGY_IP>

# View container logs
cd /volume1/docker/image_processor
docker-compose -f docker-compose.synology.yml logs -f

# Restart the app
docker-compose -f docker-compose.synology.yml restart

# Stop the app
docker-compose -f docker-compose.synology.yml down

# Manually rebuild and start (without deploy.ps1)
docker-compose -f docker-compose.synology.yml up -d --build
```

---

## Troubleshooting

| Problem                           | Solution                                                       |
|------------------------------------|----------------------------------------------------------------|
| `git: command not found`           | Install Git via Package Center or Entware                      |
| `Permission denied (publickey)`    | Set up SSH keys properly (See "Set Up SSH Access")             |
| Folders not visible in browser UI  | Check volume mounts—folders must be under `/media/`            |
| SQL Server connection errors       | Ensure Tailscale works and `DB_SERVER` is correct              |
| `ODBC Driver 17` not found         | NAS must be Intel/AMD; ARM is not supported                    |
| Port 5050 already in use           | Change the port in Dockerfile and docker-compose                |
| `.env` not found after deploy      | Script will create a template—edit it on Synology after first run |
