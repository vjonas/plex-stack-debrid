# Plex Debrid Stack

Linux home server running a media automation stack using Docker with Debrid-Link cloud downloading, Usenet via SABnzbd, and VPN-routed download traffic via Gluetun.

Once setup is complete, **all normal usage happens via Overseerr on a phone**.

---

## Architecture

```
Phone -> Overseerr -> Radarr/Sonarr -> Prowlarr (indexers)
                                    |
                            +-------+-------+
                            |               |
                        RDTClient        SABnzbd
                      (Debrid-Link)     (Usenet)
                            |               |
                        [  Gluetun VPN tunnel  ]
                            |               |
                      Debrid cloud     Usenet server
                            \               /
                             \             /
                          /mnt/downloads -> Plex
```

- **Gluetun** routes all download traffic through a NordVPN tunnel
- **RDTClient** emulates a qBittorrent API, downloads via Debrid-Link
- **SABnzbd** downloads from Usenet providers
- **ClubNZB Proxy** proxies NZB requests for ClubNZB indexer
- **Prowlarr** manages indexers and syncs them to Radarr/Sonarr
- **FlareSolverr** solves Cloudflare challenges for indexers

---

## Quick Start

### Requirements

- Linux server (Ubuntu/Debian recommended)
- Docker and Docker Compose installed
- SMB network share mounted at `/mnt/downloads`
- Debrid-Link account with API access
- NordVPN account (for VPN tunnel)

### 1. Clone and configure

```bash
git clone <repo-url> ~/git/plex-prowlr-sonar-etc-stack
cd ~/git/plex-prowlr-sonar-etc-stack
cp .env.example .env
```

Edit `.env` and fill in your credentials:

| Variable | Description |
|----------|-------------|
| `DEBRID_API_KEY` | Your Debrid-Link API key |
| `NORD_USER` | NordVPN service credential username |
| `NORD_PASS` | NordVPN service credential password |

> **NordVPN credentials**: These are NOT your regular login. Get them from
> https://my.nordaccount.com/dashboard/nordvpn/manual-configuration/service-credentials/

### 2. Mount SMB share

Set up the SMB mount (one-time):

```bash
# Create mount point
sudo mkdir -p /mnt/downloads

# Add credentials file
sudo tee /etc/smbcredentials <<EOF
username=YOUR_SMB_USER
password=YOUR_SMB_PASS
EOF
sudo chmod 600 /etc/smbcredentials

# Add to fstab for auto-mount
echo '//192.168.1.1/H /mnt/downloads cifs credentials=/etc/smbcredentials,uid=1000,gid=1000,iocharset=utf8,vers=2.0 0 0' | sudo tee -a /etc/fstab
sudo mount -a
```

### 3. Create download directories

```bash
sudo mkdir -p /mnt/downloads/debrid-link/downloads/{radarr,sonarr,tv-sonarr}
sudo mkdir -p /mnt/downloads/debrid-link/downloads/usenet/{complete/{movies,tv},incomplete}
sudo chown -R 1000:1000 /mnt/downloads/debrid-link/downloads
```

### 4. Start the stack

```bash
docker compose up -d
```

### 5. Run automated setup

```bash
./setup.sh
```

This configures root folders, remote path mappings, Prowlarr integrations, and indexers.

---

## Service URLs

| Service | Purpose | URL |
|---------|---------|-----|
| Overseerr | Phone-friendly request UI | http://your-server:5055 |
| Radarr | Movie automation | http://your-server:7878 |
| Sonarr | TV automation | http://your-server:8989 |
| Prowlarr | Indexer management | http://your-server:9696 |
| RDTClient | Debrid download client (qBit API) | http://your-server:6500 |
| SABnzbd | Usenet download client | http://your-server:8080 |
| FlareSolverr | Cloudflare solver for indexers | http://your-server:8191 |
| ClubNZB Proxy | NZB proxy for ClubNZB | http://your-server:5080 |

---

## Manual Configuration

### RDTClient (Debrid-Link)

1. Open RDTClient at `http://your-server:6500`
2. Login with your Debrid-Link API key
3. Go to **Settings** > **qBittorrent** section:
   - **Post Torrent Download Action**: `Download all files to host`
   - **Only Download Available Files**: Enabled
   - **Minimum File Size to Download**: `5` MB

### Download Client in Radarr/Sonarr

> **Important**: Since RDTClient and SABnzbd run behind the Gluetun VPN container,
> use `gluetun` as the hostname (not `rdtclient` or `sabnzbd`).

**RDTClient (torrent/debrid):**

| Setting | Radarr | Sonarr |
|---------|--------|--------|
| Type | qBittorrent | qBittorrent |
| Host | `gluetun` | `gluetun` |
| Port | `6500` | `6500` |
| Category | `radarr` | `tv-sonarr` |

**SABnzbd (usenet):**

| Setting | Radarr | Sonarr |
|---------|--------|--------|
| Type | SABnzbd | SABnzbd |
| Host | `gluetun` | `gluetun` |
| Port | `8080` | `8080` |
| Category | `movies` | `tv` |

### Prowlarr Setup

1. **FlareSolverr**: Settings > Indexers > Add Proxy > FlareSolverr
   - Host: `http://flaresolverr:8191`
2. **Apps**: Settings > Apps > Add Radarr/Sonarr
   - Prowlarr Server: `http://prowlarr:9696`
   - Radarr Server: `http://radarr:7878`
   - Sonarr Server: `http://sonarr:8989`
3. **Indexers**: Add your preferred indexers (1337x, EZTV, ThePirateBay, etc.)

### SABnzbd Setup

1. Open SABnzbd at `http://your-server:8080`
2. Run through the first-time wizard, add your Usenet server
3. Configure folders (Config > Folders):
   - Temporary: `/data/downloads/usenet/incomplete`
   - Completed: `/data/downloads/usenet/complete`
4. Configure categories (Config > Categories):
   - `movies` -> `movies`
   - `tv` -> `tv`

### Overseerr Setup

1. Open Overseerr at `http://your-server:5055`
2. Sign in using Plex account
3. Add Radarr/Sonarr servers using your server's LAN IP and their API keys

---

## VPN (Gluetun)

Download traffic from RDTClient and SABnzbd is routed through Gluetun, which connects to NordVPN via OpenVPN.

- **Kill switch**: Gluetun blocks all traffic if the VPN drops, preventing leaks
- **LAN access**: The firewall is configured to allow local network (`192.168.1.0/24`) and Docker inter-container communication even through the VPN
- **Exposed ports**: RDTClient (6500) and SABnzbd (8080) remain accessible via the host

If the VPN auth fails, the download UIs will still be reachable but downloads won't work until the VPN reconnects.

---

## File Structure

```
plex-prowlr-sonar-etc-stack/
├── docker-compose.yml        # Main stack definition
├── .env                      # Credentials (gitignored)
├── .env.example              # Credential template
├── setup.sh                  # Automated first-time setup
├── cmd.sh                    # SMB fstab helper script
├── clubnzb-proxy/            # ClubNZB proxy app (Dockerfile + app.py)
├── portainer/                # Portainer compose (optional, separate stack)
└── config/                   # Persistent container configs (gitignored)
    ├── prowlarr/
    ├── radarr/
    ├── sonarr/
    ├── overseerr/
    ├── rdtclient/
    └── sabnzbd/
```

### Config Persistence

All container configs are bind-mounted to `./config/<service>/`. This means:
- Configs survive `docker compose down` and container recreation
- You can back them up by copying the `config/` directory
- They are **gitignored** because they contain API keys, databases, and other secrets

To back up all configs:

```bash
tar czf config-backup-$(date +%Y%m%d).tar.gz config/
```

---

## Remote Path Mappings

RDTClient reports Windows-style paths internally. These mappings translate them for Radarr/Sonarr:

| RDTClient Path | Radarr/Sonarr Path |
|----------------|-------------------|
| `C:\Downloads\radarr\` | `/data/downloads/radarr/` |
| `C:\Downloads\sonarr\` | `/data/downloads/sonarr/` |
| `C:\Downloads\tv-sonarr\` | `/data/downloads/tv-sonarr/` |

These are configured automatically by `setup.sh`.

---

## Recovery (after reboot)

1. Verify SMB mount:
   ```bash
   df -h | grep downloads
   # If not mounted:
   sudo mount -a
   ```

2. Start the stack:
   ```bash
   cd ~/git/plex-prowlr-sonar-etc-stack
   docker compose up -d
   ```

3. Verify services load at their URLs above

---

## Troubleshooting

### RDTClient / SABnzbd web UI unreachable
These run behind Gluetun. If the VPN is failing (check `docker logs gluetun`), the firewall may be blocking access. The `FIREWALL_INPUT_PORTS` and `FIREWALL_OUTBOUND_SUBNETS` settings in `docker-compose.yml` should keep the UIs accessible regardless.

### Radarr/Sonarr can't connect to download client
Since RDTClient and SABnzbd share Gluetun's network, use **`gluetun`** as the hostname in download client settings, not `rdtclient` or `sabnzbd`.

### "Path does not exist" errors
Re-run `./setup.sh` to recreate download directories and path mappings.

### VPN AUTH_FAILED
Verify your NordVPN service credentials at https://my.nordaccount.com/dashboard/nordvpn/manual-configuration/service-credentials/ — these are different from your regular NordVPN login.
