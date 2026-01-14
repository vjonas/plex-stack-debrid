# Plex Debrid Stack

Mac mini home server running a media automation stack using Docker (Colima) with Debrid-Link cloud downloading.

This document covers:

- **First-time setup on a new system**
- **Daily operation & recovery**
- **Architecture & reference**

Once setup is complete, **all normal usage happens via Overseerr on a phone**.

---

## Quick Start (First-Time Setup)

### Requirements

- macOS (Apple Silicon recommended)
- SMB network share for media storage
- Debrid-Link account with API access
- Homebrew installed

---

### Install Dependencies

```bash
brew install colima docker docker-compose
```

Start Docker runtime:

```bash
colima start
```

Verify Docker:

```bash
docker info
```

---

### SMB Share Setup

Mount the SMB share via Finder (easiest on macOS):

1. Open Finder
2. Press **Cmd+K**
3. Enter: `smb://192.168.1.1/H` (replace with your NAS IP/share)
4. Enter credentials when prompted
5. It will mount at `/Volumes/tp-share` (or similar)

Update the paths in `docker-compose.yml` if your mount point differs.

---

### First Start

```bash
# Clone or navigate to the repo
cd ~/git/plex-stack-debrid

# Start the stack
docker compose up -d

# Run the automated setup script
./setup.sh
```

The setup script will:
- Wait for all services to start
- Configure root folders in Radarr/Sonarr
- Set up remote path mappings (RDTClient → arr apps)
- Connect Prowlarr to Radarr/Sonarr
- Add FlareSolverr proxy
- Add public indexers (EZTV, ThePirateBay, 1337x) to Prowlarr
- **Add indexers directly to Radarr/Sonarr databases** (bypasses API validation issues)

---

## Manual Configuration (if needed)

### RDTClient Setup (Debrid-Link)

1. Open RDTClient at `http://localhost:6500`
2. Login with your Debrid-Link API key
3. Go to **Settings** → **qBittorrent** section:
   - **Post Torrent Download Action**: `Download all files to host`
   - **Category**: Leave empty or set per-app
   - **Only Download Available Files**: Enabled
   - **Minimum File Size to Download**: `5` MB

---

### Radarr Setup (Movies)

1. Open Radarr at `http://localhost:7878`
2. Settings → Download Clients → Add:
   - **Type**: qBittorrent
   - **Host**: `rdtclient`
   - **Port**: `6500`
   - **Username/Password**: (from RDTClient login)
   - **Category**: `radarr`

---

### Sonarr Setup (TV)

1. Open Sonarr at `http://localhost:8989`
2. Settings → Download Clients → Add:
   - **Type**: qBittorrent
   - **Host**: `rdtclient`
   - **Port**: `6500`
   - **Username/Password**: (from RDTClient login)
   - **Category**: `tv-sonarr`

---

### Overseerr Setup

1. Open Overseerr at `http://localhost:5055`
2. Sign in using Plex account
3. Add Radarr server:
   - **Hostname**: `192.168.1.159` (or your host IP)
   - **Port**: `7878`
   - **API Key**: (from Radarr Settings → General)
4. Add Sonarr server similarly
5. Enable auto-approval for requests

---

## Architecture Overview

```
Phone → Overseerr → Radarr/Sonarr → RDTClient → Debrid-Link Cloud → HTTP Download → SMB NAS → Plex
```

- **Plex** runs natively on macOS
- **Docker stack (Colima)** handles automation
- **Debrid-Link** caches torrents in the cloud (no torrents on your network)
- **RDTClient** emulates qBittorrent API, downloads via HTTP to NAS

---

## Service URLs

| Service      | Purpose                           | URL                    |
| ------------ | --------------------------------- | ---------------------- |
| Overseerr    | Phone-friendly request UI         | http://localhost:5055  |
| Radarr       | Movie automation                  | http://localhost:7878  |
| Sonarr       | TV automation                     | http://localhost:8989  |
| Prowlarr     | Indexer management                | http://localhost:9696  |
| RDTClient    | Debrid download client (qBit API) | http://localhost:6500  |
| FlareSolverr | Cloudflare solver for trackers    | http://localhost:8191  |

---

## File Structure

```
plex-stack-debrid/
├── docker-compose.yml      # Main stack definition
├── setup.sh                # Automated configuration script
├── config/
│   ├── path-mappings.json  # RDTClient → arr path translations
│   └── prowlarr-apps.json  # Prowlarr app/indexer config
└── README.md
```

---

## Media Folders (SMB Share)

```
/Volumes/tp-share/debrid-link/
├── movies/                 # Radarr library (Plex Movies)
├── tvshows/                # Sonarr library (Plex TV Shows)
└── downloads/              # Temporary staging
    ├── radarr/             # Movie downloads in progress
    ├── sonarr/             # TV downloads in progress
    └── tv-sonarr/          # Alternative TV category
```

---

## Remote Path Mappings

RDTClient reports Windows-style paths. These mappings translate them for the arr apps:

| RDTClient Path           | Radarr/Sonarr Path      |
| ------------------------ | ----------------------- |
| `C:\Downloads\radarr\`   | `/downloads/radarr/`    |
| `C:\Downloads\sonarr\`   | `/downloads/sonarr/`    |
| `C:\Downloads\tv-sonarr\`| `/downloads/tv-sonarr/` |

These are configured automatically by `setup.sh`.

---

## Recovery Checklist (after crash/reboot)

1. **Mount SMB share** via Finder (Cmd+K → `smb://192.168.1.1/H`)

2. **Start the stack**:
   ```bash
   colima start
   cd ~/git/plex-stack-debrid
   docker compose up -d
   ```

3. **Verify services**:
   - Overseerr loads at http://localhost:5055
   - RDTClient shows connected to Debrid-Link
   - No health warnings in Radarr/Sonarr

---

## Troubleshooting

### "Path does not exist" errors
Run `./setup.sh` to recreate download directories and path mappings.

### Indexer sync issues / "No indexers available"
Prowlarr's automatic sync to Radarr/Sonarr often fails due to strict API validation. The setup script handles this by adding indexers directly to the databases. If you still have issues:

```bash
# Re-run setup to add indexers directly
./setup.sh
```

Or manually add via database:
```bash
docker exec radarr apk add --no-cache sqlite
docker exec radarr sqlite3 /config/radarr.db "SELECT Name FROM Indexers;"
```

### RDTClient authentication fails
The qBittorrent API in RDTClient uses your Debrid-Link login. Try leaving username blank and using API key as password, or check RDTClient's Account settings.

### SMB mount permission denied
Mount via Finder instead of command line for proper user permissions.






SETUPPPPPPPPP

========================================
 Setup Steps


  1. Configure FlareSolverr in Prowlarr

  1. Open Prowlarr at http://your-server:9696
  2. Go to Settings → Indexers
  3. Click + under "Indexer Proxies"
  4. Select FlareSolverr
  5. Set:
    • Name: FlareSolverr
    • Host: http://flaresolverr:8191
    • Tags: leave empty (applies to all) or create a tag for specific indexers
  6. Click Test then Save


  2. Add Indexers in Prowlarr

  1. In Prowlarr, go to Indexers
  2. Click Add Indexer
  3. Search for your preferred indexers (e.g., 1337x, RARBG, TorrentGalaxy, etc.)
  4. Configure each indexer with any required credentials
  5. If an indexer has Cloudflare protection, tag it to use FlareSolverr


  3. Connect Prowlarr to Radarr & Sonarr

  1. In Prowlarr, go to Settings → Apps
  2. Click + and select Radarr:
    • Name: Radarr
    • Sync Level: Full Sync
    • Prowlarr Server: http://prowlarr:9696
    • Radarr Server: http://radarr:7878
    • API Key: (get from Radarr → Settings → General)
  3. Click Test then Save
  4. Repeat for Sonarr:
    • Sonarr Server: http://sonarr:8989
    • API Key: (get from Sonarr → Settings → General)


  4. Sync Indexers

  1. In Prowlarr, click Sync App Indexers (or it syncs automatically)
  2. Your indexers will now appear in Radarr and Sonarr automatically


  5. Configure Download Client in Radarr/Sonarr

  1. In Radarr → Settings → Download Clients
  2. Click + and add your RDTClient (or whatever download client you use)
  3. Repeat for Sonarr

  ---

  Quick Reference - URLs (internal Docker network)

  | Service | Internal URL | External URL |
  |---------|--------------|--------------|
  | FlareSolverr | http://flaresolverr:8191 | http://your-server:8191 |
  | Prowlarr | http://prowlarr:9696 | http://your-server:9696 |
  | Radarr | http://radarr:7878 | http://your-server:7878 |
  | Sonarr | http://sonarr:8989 | http://your-server:8989 |
  | RDTClient | http://rdtclient:6500 | http://your-server:6500 |
  Use the internal URLs when services talk to each other inside Docker.
--------------------------------------------------------------------
