#!/bin/bash
# Setup script for Plex Debrid Stack
# Run this after `docker compose up -d` to configure all services

set -e

CONFIG_DIR="$(dirname "$0")/config"

echo "=== Plex Debrid Stack Setup ==="
echo ""

# Prompt for SMB mount path
DEFAULT_SMB_PATH="/Volumes/tp-share"
read -p "Enter SMB mount path [$DEFAULT_SMB_PATH]: " SMB_PATH
SMB_PATH="${SMB_PATH:-$DEFAULT_SMB_PATH}"

# Verify SMB mount exists
if [ ! -d "$SMB_PATH" ]; then
    echo ""
    echo "ERROR: SMB path '$SMB_PATH' does not exist!"
    echo "Please mount your SMB share first:"
    echo "  1. Open Finder"
    echo "  2. Press Cmd+K"
    echo "  3. Enter: smb://your-nas-ip/share"
    echo ""
    exit 1
fi

echo "Using SMB path: $SMB_PATH"
echo ""

# Wait for services to be ready
wait_for_service() {
    local name=$1
    local url=$2
    local max_attempts=30
    local attempt=1
    
    echo -n "Waiting for $name..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo " ready!"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    echo " timeout!"
    return 1
}

# Get API key from container config
get_api_key() {
    local container=$1
    docker exec "$container" cat /config/config.xml 2>/dev/null | grep ApiKey | sed 's/.*<ApiKey>\(.*\)<\/ApiKey>.*/\1/'
}

echo "Step 1: Waiting for services to start..."
wait_for_service "Radarr" "http://localhost:7878"
wait_for_service "Sonarr" "http://localhost:8989"
wait_for_service "Prowlarr" "http://localhost:9696"
wait_for_service "RDTClient" "http://localhost:6500"

echo ""
echo "Step 2: Getting API keys..."
RADARR_API=$(get_api_key radarr)
SONARR_API=$(get_api_key sonarr)
PROWLARR_API=$(get_api_key prowlarr)

echo "  Radarr API: ${RADARR_API:0:8}..."
echo "  Sonarr API: ${SONARR_API:0:8}..."
echo "  Prowlarr API: ${PROWLARR_API:0:8}..."

# Create download directories
echo ""
echo "Step 3: Creating download directories..."
mkdir -p "$SMB_PATH/debrid-link/downloads/radarr"
mkdir -p "$SMB_PATH/debrid-link/downloads/sonarr"
mkdir -p "$SMB_PATH/debrid-link/downloads/tv-sonarr"
echo "  Created: $SMB_PATH/debrid-link/downloads/{radarr,sonarr,tv-sonarr}"

# Configure Radarr root folder
echo ""
echo "Step 4: Configuring Radarr..."
RADARR_ROOTS=$(curl -s "http://localhost:7878/api/v3/rootfolder" -H "X-Api-Key: $RADARR_API")
if [ "$RADARR_ROOTS" = "[]" ]; then
    echo "  Adding root folder /movies..."
    curl -s -X POST "http://localhost:7878/api/v3/rootfolder" \
        -H "X-Api-Key: $RADARR_API" \
        -H "Content-Type: application/json" \
        -d '{"path": "/movies"}' > /dev/null
fi

# Add Radarr path mappings
echo "  Adding remote path mappings..."
curl -s -X POST "http://localhost:7878/api/v3/remotepathmapping" \
    -H "X-Api-Key: $RADARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "host": "rdtclient",
        "remotePath": "C:\\Downloads\\radarr\\",
        "localPath": "/downloads/radarr/"
    }' > /dev/null 2>&1 || true
echo "  Done!"

# Configure Sonarr root folder
echo ""
echo "Step 5: Configuring Sonarr..."
SONARR_ROOTS=$(curl -s "http://localhost:8989/api/v3/rootfolder" -H "X-Api-Key: $SONARR_API")
if [ "$SONARR_ROOTS" = "[]" ]; then
    echo "  Adding root folder /tv..."
    curl -s -X POST "http://localhost:8989/api/v3/rootfolder" \
        -H "X-Api-Key: $SONARR_API" \
        -H "Content-Type: application/json" \
        -d '{"path": "/tv"}' > /dev/null
fi

# Add Sonarr path mappings
echo "  Adding remote path mappings..."
curl -s -X POST "http://localhost:8989/api/v3/remotepathmapping" \
    -H "X-Api-Key: $SONARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "host": "rdtclient",
        "remotePath": "C:\\Downloads\\sonarr\\",
        "localPath": "/downloads/sonarr/"
    }' > /dev/null 2>&1 || true

curl -s -X POST "http://localhost:8989/api/v3/remotepathmapping" \
    -H "X-Api-Key: $SONARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "host": "rdtclient",
        "remotePath": "C:\\Downloads\\tv-sonarr\\",
        "localPath": "/downloads/tv-sonarr/"
    }' > /dev/null 2>&1 || true
echo "  Done!"

# Configure Prowlarr
echo ""
echo "Step 6: Configuring Prowlarr..."

# Add FlareSolverr
echo "  Adding FlareSolverr proxy..."
curl -s -X POST "http://localhost:9696/api/v1/indexerproxy" \
    -H "X-Api-Key: $PROWLARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "FlareSolverr",
        "implementation": "FlareSolverr",
        "configContract": "FlareSolverrSettings",
        "fields": [
            {"name": "host", "value": "http://flaresolverr:8191/"},
            {"name": "requestTimeout", "value": 60}
        ],
        "tags": []
    }' > /dev/null 2>&1 || true

# Add Radarr app
echo "  Adding Radarr application..."
curl -s -X POST "http://localhost:9696/api/v1/applications" \
    -H "X-Api-Key: $PROWLARR_API" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"Radarr\",
        \"syncLevel\": \"fullSync\",
        \"implementation\": \"Radarr\",
        \"configContract\": \"RadarrSettings\",
        \"fields\": [
            {\"name\": \"prowlarrUrl\", \"value\": \"http://prowlarr:9696\"},
            {\"name\": \"baseUrl\", \"value\": \"http://radarr:7878\"},
            {\"name\": \"apiKey\", \"value\": \"$RADARR_API\"},
            {\"name\": \"syncCategories\", \"value\": [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060]}
        ],
        \"tags\": []
    }" > /dev/null 2>&1 || true

# Add Sonarr app
echo "  Adding Sonarr application..."
curl -s -X POST "http://localhost:9696/api/v1/applications" \
    -H "X-Api-Key: $PROWLARR_API" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"Sonarr\",
        \"syncLevel\": \"fullSync\",
        \"implementation\": \"Sonarr\",
        \"configContract\": \"SonarrSettings\",
        \"fields\": [
            {\"name\": \"prowlarrUrl\", \"value\": \"http://prowlarr:9696\"},
            {\"name\": \"baseUrl\", \"value\": \"http://sonarr:8989\"},
            {\"name\": \"apiKey\", \"value\": \"$SONARR_API\"},
            {\"name\": \"syncCategories\", \"value\": [5000, 5010, 5020, 5030, 5040, 5045, 5050, 5070]}
        ],
        \"tags\": []
    }" > /dev/null 2>&1 || true

# Add indexers
echo "  Adding indexers..."
curl -s -X POST "http://localhost:9696/api/v1/indexer" \
    -H "X-Api-Key: $PROWLARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "EZTV",
        "definitionName": "eztv",
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "enable": true,
        "protocol": "torrent",
        "priority": 25,
        "appProfileId": 1,
        "fields": [{"name": "definitionFile", "value": "eztv"}]
    }' > /dev/null 2>&1 || true

curl -s -X POST "http://localhost:9696/api/v1/indexer" \
    -H "X-Api-Key: $PROWLARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "ThePirateBay",
        "definitionName": "thepiratebay",
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "enable": true,
        "protocol": "torrent",
        "priority": 25,
        "appProfileId": 1,
        "fields": [{"name": "definitionFile", "value": "thepiratebay"}]
    }' > /dev/null 2>&1 || true

echo "  Done!"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Configuration:"
echo "  SMB Path:    $SMB_PATH"
echo "  Downloads:   $SMB_PATH/debrid-link/downloads/"
echo ""
echo "Service URLs:"
echo "  Overseerr:   http://localhost:5055"
echo "  Radarr:      http://localhost:7878"
echo "  Sonarr:      http://localhost:8989"
echo "  Prowlarr:    http://localhost:9696"
echo "  RDTClient:   http://localhost:6500"
echo ""
echo "API Keys:"
echo "  Radarr:   $RADARR_API"
echo "  Sonarr:   $SONARR_API"
echo "  Prowlarr: $PROWLARR_API"
echo ""
echo "Next steps:"
echo "  1. Configure RDTClient with your Debrid-Link API key at http://localhost:6500"
echo "  2. Add RDTClient as download client in Radarr/Sonarr:"
echo "     - Type: qBittorrent"
echo "     - Host: rdtclient"
echo "     - Port: 6500"
echo "     - Username/Password: (from RDTClient)"
echo "  3. Configure Overseerr to connect to Radarr/Sonarr"
echo ""
