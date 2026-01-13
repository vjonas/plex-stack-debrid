# Plex

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
- External drive for media (APFS or HFS+ recommended)
- SMB network share for debrid downloads
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

Mount the SMB share where Debrid-Link downloads will be stored:

```bash
# Create mount point
sudo mkdir -p /Volumes/debrid-downloads

# Mount SMB share (replace IP and credentials)
sudo mount -t smbfs '//username:password@192.168.1.1/H' /Volumes/debrid-downloads

# Or with SMB version specified:
sudo mount -t smbfs -o vers=2.0 '//username:password@192.168.1.1/H' /Volumes/debrid-downloads
```

For persistent mounting, create `/etc/auto_smb`:

```bash
# /etc/auto_smb
debrid-downloads -fstype=smbfs,soft ://username:password@192.168.1.1/H
```

Then add to `/etc/auto_master`:

```
/Volumes auto_smb
```

And reload automount:

```bash
sudo automount -vc
```

Alternatively, connect via Finder (Cmd+K → `smb://192.168.1.1/H`) and it will mount at `/Volumes/H`.

---

### Media Folder Setup

Create media folders on the external drive:

```
/Volumes/storage/Media
├── Movies
└── TV Shows
```

Enable ownership on the drive (recommended):

```bash
sudo diskutil enableOwnership /Volumes/storage
```

---

### Docker Stack Setup

Place the provided `docker-compose.yml` in:

```
~/docker/servarr
```

Create the folder if needed:

```bash
mkdir -p ~/docker/servarr
cd ~/docker/servarr
```

---

### First Start

```bash
colima start
cd ~/docker/servarr
docker-compose up -d
```

Verify containers:

```bash
docker-compose ps
```

---

## Initial Service Configuration (One-Time)

Open each service in a browser:

| Service     | URL                   |
| ----------- | --------------------- |
| Overseerr   | http://<host-ip>:5055 |
| Radarr      | http://<host-ip>:7878 |
| Sonarr      | http://<host-ip>:8989 |
| Prowlarr    | http://<host-ip>:9696 |
| RDTClient   | http://<host-ip>:6500 |

---

### RDTClient Setup (Debrid-Link)

1. Open RDTClient at `http://<host-ip>:6500`
2. Create admin credentials on first login
3. Go to **Settings** and configure:
   - **Provider**: Select `DebridLink`
   - **API Key**: Enter your Debrid-Link API key (get from [debrid-link.com](https://debrid-link.com))
   - **Download path**: `/data/downloads`
   - **Mapped path**: `/Volumes/debrid-downloads` (for arr apps to find files)
   - **Post Torrent Download Action**: `Download all files to host`
   - **Only Download Available Files**: Enabled
   - **Minimum File Size to Download**: `5` MB (avoid small files)
4. Create categories:
   - `radarr` → for movies
   - `sonarr` → for TV shows

---

### Prowlarr (Indexers)

Add public indexers:

- **YTS** → Movies → tag `movies`
- **EZTV** → TV → tag `tv`
- **BitSearch** → Movies + TV → tags `movies`, `tv`

Ensure all indexers test **green**.

Prowlarr automatically syncs indexers to Radarr and Sonarr.

---

### Radarr Setup (Movies)

- Root folder: `/movies`
- Add RDTClient as download client:
  - **Type**: qBittorrent (RDTClient emulates qBit API)
  - **Host**: `rdtclient`
  - **Port**: `6500`
  - **Category**: `radarr`
- Enable upgrades in quality profile

---

### Sonarr Setup (TV)

- Root folder: `/tv`
- Add RDTClient as download client:
  - **Type**: qBittorrent (RDTClient emulates qBit API)
  - **Host**: `rdtclient`
  - **Port**: `6500`
  - **Category**: `sonarr`
- Enable upgrades in quality profile

---

### Plex Integration

In **Radarr** and **Sonarr**:

- Settings → Connect → Plex Media Server
- Host: Plex server IP
- Port: `32400`
- Token: Plex API token
- Trigger: **On Import**

This ensures Plex updates automatically when downloads complete.

---

### Overseerr Setup (User Interface)

- Sign in using Plex account
- Connect Radarr and Sonarr
- Enable auto-approval for requests
- Users authenticate via Plex login

Phone usage:

- Open Overseerr in mobile browser
- Add to home screen for app-like UX

---

### Test

Request:

- One movie
- One TV episode

Confirm:

- Debrid-Link shows torrent cached
- RDTClient downloads files to SMB share
- File moves to Movies / TV Shows
- Plex updates automatically

---

## Architecture Overview

- **Plex** runs natively on macOS
- **Docker stack (Colima)** handles automation and downloads
- **Debrid-Link** handles torrent caching in the cloud (no torrents on your network)
- **RDTClient** downloads cached files via HTTP to your NAS
- **Requests are done via phone (Overseerr)**

Flow:

```
Phone → Overseerr → Radarr/Sonarr → RDTClient → Debrid-Link Cloud → HTTP Download → SMB NAS → Plex
```

---

## Media Folders

```
/Volumes/storage/Media
├── Movies
└── TV Shows

/Volumes/debrid-downloads (SMB mount)
└── (temporary download staging)
```

- **Movies / TV Shows** → Plex libraries
- **debrid-downloads** → Temporary staging from Debrid-Link (not scanned by Plex)

---

## Docker Stack Location

```
~/docker/servarr
```

Start stack (manual):

```bash
colima start
cd ~/docker/servarr
docker-compose up -d
```

Stop stack:

```bash
docker-compose down
```

---

## Running Services

| Service      | Purpose                           | URL / Port             |
| ------------ | --------------------------------- | ---------------------- |
| Plex         | Media playback                    | http://<host-ip>:32400 |
| Overseerr    | Phone-friendly request UI         | http://<host-ip>:5055  |
| Radarr       | Movie automation                  | http://<host-ip>:7878  |
| Sonarr       | TV automation                     | http://<host-ip>:8989  |
| Prowlarr     | Indexer management                | http://<host-ip>:9696  |
| RDTClient    | Debrid download client (qBit API) | http://<host-ip>:6500  |
| FlareSolverr | Cloudflare solver for trackers    | internal (8191)        |

---

## Debrid-Link Setup

Debrid-Link is a cloud-based service that:

1. Caches torrents on their servers (no torrents on your network)
2. Provides direct HTTP download links for cached files
3. Keeps files available for re-download

Get your API key from: https://debrid-link.com/webapp/apikey

RDTClient uses this API to:
- Submit torrents to Debrid-Link
- Monitor download progress
- Download completed files to your NAS via HTTP
- Report status back to Radarr/Sonarr

---

## Categories (RDTClient)

Configure in RDTClient settings:

- `radarr` → Movies
- `sonarr` → TV Shows

Radarr uses category `radarr`  
Sonarr uses category `sonarr`

---

## Recovery Checklist (after crash/reboot)

1. Verify SMB share is mounted:
   ```bash
   ls /Volumes/debrid-downloads
   ```
   If not mounted, remount:
   ```bash
   sudo mount -t smbfs '//username:password@192.168.1.1/H' /Volumes/debrid-downloads
   ```

2. Start Colima and Docker stack:
   ```bash
   colima start
   cd ~/docker/servarr
   docker-compose up -d
   ```

3. Verify:
   - Overseerr loads
   - RDTClient reachable and shows connected to Debrid-Link
   - SMB mount accessible from containers
