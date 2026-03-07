#!/bin/bash
# Setup script for Plex Debrid Stack
# Run this after `docker compose up -d` to configure all services

set -e

echo "=== Plex Debrid Stack Setup ==="
echo ""

DOWNLOADS_PATH="/mnt/downloads/debrid-link"

if [ ! -d "$DOWNLOADS_PATH" ]; then
    echo "ERROR: Downloads path '$DOWNLOADS_PATH' does not exist!"
    echo "Please mount your SMB share first: sudo mount -a"
    exit 1
fi

echo "Using downloads path: $DOWNLOADS_PATH"
echo ""

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

echo ""
echo "Step 3: Creating download directories..."
mkdir -p "$DOWNLOADS_PATH/downloads/radarr"
mkdir -p "$DOWNLOADS_PATH/downloads/sonarr"
mkdir -p "$DOWNLOADS_PATH/downloads/tv-sonarr"
mkdir -p "$DOWNLOADS_PATH/downloads/usenet/complete/movies"
mkdir -p "$DOWNLOADS_PATH/downloads/usenet/complete/tv"
mkdir -p "$DOWNLOADS_PATH/downloads/usenet/incomplete"
echo "  Created download directories"

echo ""
echo "Step 4: Configuring Radarr..."
RADARR_ROOTS=$(curl -s "http://localhost:7878/api/v3/rootfolder" -H "X-Api-Key: $RADARR_API")
if [ "$RADARR_ROOTS" = "[]" ]; then
    echo "  Adding root folder /data..."
    curl -s -X POST "http://localhost:7878/api/v3/rootfolder" \
        -H "X-Api-Key: $RADARR_API" \
        -H "Content-Type: application/json" \
        -d '{"path": "/data"}' > /dev/null
fi

echo "  Adding remote path mappings..."
curl -s -X POST "http://localhost:7878/api/v3/remotepathmapping" \
    -H "X-Api-Key: $RADARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "host": "gluetun",
        "remotePath": "C:\\Downloads\\radarr\\",
        "localPath": "/data/downloads/radarr/"
    }' > /dev/null 2>&1 || true
echo "  Done!"

echo ""
echo "Step 5: Configuring Sonarr..."
SONARR_ROOTS=$(curl -s "http://localhost:8989/api/v3/rootfolder" -H "X-Api-Key: $SONARR_API")
if [ "$SONARR_ROOTS" = "[]" ]; then
    echo "  Adding root folder /data..."
    curl -s -X POST "http://localhost:8989/api/v3/rootfolder" \
        -H "X-Api-Key: $SONARR_API" \
        -H "Content-Type: application/json" \
        -d '{"path": "/data"}' > /dev/null
fi

echo "  Adding remote path mappings..."
curl -s -X POST "http://localhost:8989/api/v3/remotepathmapping" \
    -H "X-Api-Key: $SONARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "host": "gluetun",
        "remotePath": "C:\\Downloads\\sonarr\\",
        "localPath": "/data/downloads/sonarr/"
    }' > /dev/null 2>&1 || true

curl -s -X POST "http://localhost:8989/api/v3/remotepathmapping" \
    -H "X-Api-Key: $SONARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "host": "gluetun",
        "remotePath": "C:\\Downloads\\tv-sonarr\\",
        "localPath": "/data/downloads/tv-sonarr/"
    }' > /dev/null 2>&1 || true
echo "  Done!"

echo ""
echo "Step 6: Configuring Prowlarr..."

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

curl -s -X POST "http://localhost:9696/api/v1/indexer" \
    -H "X-Api-Key: $PROWLARR_API" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "1337x",
        "definitionName": "1337x",
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "enable": true,
        "protocol": "torrent",
        "priority": 25,
        "appProfileId": 1,
        "fields": [{"name": "definitionFile", "value": "1337x"}]
    }' > /dev/null 2>&1 || true
echo "  Done!"

echo ""
echo "Step 7: Adding indexers directly to Radarr/Sonarr..."

echo "  Getting Prowlarr indexer IDs..."
TPB_ID=$(curl -s "http://localhost:9696/api/v1/indexer" -H "X-Api-Key: $PROWLARR_API" | \
    python3 -c "import sys,json; indexers=json.load(sys.stdin); print(next((i['id'] for i in indexers if 'piratebay' in i.get('name','').lower()), ''))" 2>/dev/null || echo "")
EZTV_ID=$(curl -s "http://localhost:9696/api/v1/indexer" -H "X-Api-Key: $PROWLARR_API" | \
    python3 -c "import sys,json; indexers=json.load(sys.stdin); print(next((i['id'] for i in indexers if 'eztv' in i.get('name','').lower()), ''))" 2>/dev/null || echo "")
X1337_ID=$(curl -s "http://localhost:9696/api/v1/indexer" -H "X-Api-Key: $PROWLARR_API" | \
    python3 -c "import sys,json; indexers=json.load(sys.stdin); print(next((i['id'] for i in indexers if '1337' in i.get('name','').lower()), ''))" 2>/dev/null || echo "")

echo "  Installing sqlite in containers..."
docker exec radarr apk add --no-cache sqlite > /dev/null 2>&1 || true
docker exec sonarr apk add --no-cache sqlite > /dev/null 2>&1 || true

echo "  Adding indexers to Radarr..."
if [ -n "$TPB_ID" ]; then
    docker exec radarr sqlite3 /config/radarr.db "INSERT OR IGNORE INTO Indexers (Name, Implementation, Settings, ConfigContract, EnableRss, EnableAutomaticSearch, EnableInteractiveSearch, Priority, Tags) VALUES ('ThePirateBay', 'Torznab', '{\"baseUrl\": \"http://prowlarr:9696/$TPB_ID/\", \"apiPath\": \"/api\", \"apiKey\": \"$PROWLARR_API\", \"categories\": [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060], \"minimumSeeders\": 1}', 'TorznabSettings', 1, 1, 1, 25, '[]');" 2>/dev/null || true
fi
if [ -n "$X1337_ID" ]; then
    docker exec radarr sqlite3 /config/radarr.db "INSERT OR IGNORE INTO Indexers (Name, Implementation, Settings, ConfigContract, EnableRss, EnableAutomaticSearch, EnableInteractiveSearch, Priority, Tags) VALUES ('1337x', 'Torznab', '{\"baseUrl\": \"http://prowlarr:9696/$X1337_ID/\", \"apiPath\": \"/api\", \"apiKey\": \"$PROWLARR_API\", \"categories\": [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060], \"minimumSeeders\": 1}', 'TorznabSettings', 1, 1, 1, 25, '[]');" 2>/dev/null || true
fi

echo "  Adding indexers to Sonarr..."
if [ -n "$TPB_ID" ]; then
    docker exec sonarr sqlite3 /config/sonarr.db "INSERT OR IGNORE INTO Indexers (Name, Implementation, Settings, ConfigContract, EnableRss, EnableAutomaticSearch, EnableInteractiveSearch, Priority, Tags) VALUES ('ThePirateBay', 'Torznab', '{\"baseUrl\": \"http://prowlarr:9696/$TPB_ID/\", \"apiPath\": \"/api\", \"apiKey\": \"$PROWLARR_API\", \"categories\": [5000, 5010, 5020, 5030, 5040, 5045, 5050, 5070], \"minimumSeeders\": 1}', 'TorznabSettings', 1, 1, 1, 25, '[]');" 2>/dev/null || true
fi
if [ -n "$EZTV_ID" ]; then
    docker exec sonarr sqlite3 /config/sonarr.db "INSERT OR IGNORE INTO Indexers (Name, Implementation, Settings, ConfigContract, EnableRss, EnableAutomaticSearch, EnableInteractiveSearch, Priority, Tags) VALUES ('EZTV', 'Torznab', '{\"baseUrl\": \"http://prowlarr:9696/$EZTV_ID/\", \"apiPath\": \"/api\", \"apiKey\": \"$PROWLARR_API\", \"categories\": [5000, 5010, 5020, 5030, 5040, 5045, 5050, 5070], \"minimumSeeders\": 1}', 'TorznabSettings', 1, 1, 1, 25, '[]');" 2>/dev/null || true
fi
if [ -n "$X1337_ID" ]; then
    docker exec sonarr sqlite3 /config/sonarr.db "INSERT OR IGNORE INTO Indexers (Name, Implementation, Settings, ConfigContract, EnableRss, EnableAutomaticSearch, EnableInteractiveSearch, Priority, Tags) VALUES ('1337x', 'Torznab', '{\"baseUrl\": \"http://prowlarr:9696/$X1337_ID/\", \"apiPath\": \"/api\", \"apiKey\": \"$PROWLARR_API\", \"categories\": [5000, 5010, 5020, 5030, 5040, 5045, 5050, 5070], \"minimumSeeders\": 1}', 'TorznabSettings', 1, 1, 1, 25, '[]');" 2>/dev/null || true
fi

echo "  Restarting Radarr and Sonarr..."
docker restart radarr sonarr > /dev/null 2>&1

sleep 10
wait_for_service "Radarr" "http://localhost:7878"
wait_for_service "Sonarr" "http://localhost:8989"
echo "  Done!"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Service URLs:"
echo "  Overseerr:    http://localhost:5055"
echo "  Radarr:       http://localhost:7878"
echo "  Sonarr:       http://localhost:8989"
echo "  Prowlarr:     http://localhost:9696"
echo "  RDTClient:    http://localhost:6500"
echo "  SABnzbd:      http://localhost:8080"
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
echo "     - Host: gluetun  (NOT rdtclient — it shares gluetun's network)"
echo "     - Port: 6500"
echo "  3. Add SABnzbd as download client in Radarr/Sonarr:"
echo "     - Host: gluetun  (NOT sabnzbd — it shares gluetun's network)"
echo "     - Port: 8080"
echo "  4. Configure Overseerr to connect to Radarr/Sonarr"
echo ""
