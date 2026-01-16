"""
ClubNZB Proxy - Newznab API wrapper for clubnzb.com (Spotweb)
Allows Prowlarr/Radarr/Sonarr to search clubnzb.com
"""

import hashlib
import re
import urllib.parse
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, Response
from fastapi.responses import StreamingResponse

app = FastAPI(title="ClubNZB Proxy", version="1.0.0")

BASE_URL = "https://www.clubnzb.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ClubNZB (Spotweb) category mappings to Newznab standard categories
# cat0_z0 = Image/Movies, cat0_z1 = Series/TV, cat0_z2 = Books, cat0_z3 = Music
CLUBNZB_TO_NEWZNAB = {
    "spotcat0_z0": "2000",  # Movies
    "spotcat0_z1": "5000",  # TV Series
    "spotcat0_z2": "7000",  # Books
    "spotcat0_z3": "3000",  # Audio/Music
    "spotcat1": "3000",     # Music
    "spotcat2": "4000",     # Games
    "spotcat3": "4000",     # Applications
}

NEWZNAB_TO_CLUBNZB = {
    # Movies
    "2000": "cat0_z0",
    "2010": "cat0_z0",
    "2020": "cat0_z0",
    "2030": "cat0_z0",
    "2040": "cat0_z0",
    "2045": "cat0_z0",
    "2050": "cat0_z0",
    # TV
    "5000": "cat0_z1",
    "5010": "cat0_z1",
    "5020": "cat0_z1",
    "5030": "cat0_z1",
    "5040": "cat0_z1",
    "5045": "cat0_z1",
    "5050": "cat0_z1",
    "5060": "cat0_z1",
    "5070": "cat0_z1",
    "5080": "cat0_z1",
}


def generate_guid(message_id: str) -> str:
    """Generate a unique GUID from message ID"""
    return hashlib.md5(message_id.encode()).hexdigest()


def parse_size(size_str: str) -> int:
    """Convert size string like '36.85 MB' to bytes"""
    if not size_str:
        return 0
    
    size_str = size_str.upper().strip()
    
    multipliers = {
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }
    
    for suffix, multiplier in multipliers.items():
        if suffix in size_str:
            try:
                num = float(re.sub(r"[^\d.]", "", size_str.replace(suffix, "").strip()))
                return int(num * multiplier)
            except ValueError:
                pass
    
    return 0


def parse_clubnzb_category(row_classes: str) -> str:
    """Convert Spotweb row classes to Newznab category"""
    for cls, newznab_cat in CLUBNZB_TO_NEWZNAB.items():
        if cls in row_classes:
            return newznab_cat
    return "5000"  # Default to TV


async def search_clubnzb(query: str, category: Optional[str] = None) -> list[dict]:
    """
    Search clubnzb.com and return parsed results
    """
    results = []
    
    # Build search URL - ClubNZB uses Spotweb format
    # Format: search[value][]=Title:=:DEF:searchterm for exact-ish match
    # Use ~cat0_z1 for TV Series category (the ~ prefix is important)
    
    # Determine category tree
    cat_tree = ""
    if category and category in NEWZNAB_TO_CLUBNZB:
        cat_tree = "~" + NEWZNAB_TO_CLUBNZB[category]  # Prefix with ~ for Spotweb
    
    # Build URL parts
    parts = [
        f"search[value][]=Title:=:DEF:{urllib.parse.quote(query)}",
        "sortby=stamp",
        "sortdir=DESC",
    ]
    
    if cat_tree:
        parts.insert(0, f"search[tree]={cat_tree}")
    
    search_url = f"{BASE_URL}/?" + "&".join(parts)
    
    print(f"[ClubNZB] Searching: {search_url}")
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        headers = {"User-Agent": USER_AGENT}
        
        try:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as e:
            print(f"[ClubNZB] Error fetching search results: {e}")
            return results
        
        soup = BeautifulSoup(response.text, "lxml")
        
        # Find all result rows in the spots table
        rows = soup.select("table.spots tbody#spots tr")
        
        print(f"[ClubNZB] Found {len(rows)} results")
        
        for row in rows:
            try:
                # Get row classes for category detection
                row_classes = " ".join(row.get("class", []))
                
                # Extract title from td.title a.spotlink
                title_elem = row.select_one("td.title a.spotlink")
                if not title_elem:
                    continue
                
                title = title_elem.get("title") or title_elem.text.strip()
                if not title:
                    continue
                
                # Get detail link
                detail_link = title_elem.get("href", "")
                if detail_link and not detail_link.startswith("http"):
                    detail_link = BASE_URL + "/" + detail_link.lstrip("/")
                
                # Extract NZB download link from td.nzb a
                nzb_elem = row.select_one("td.nzb a")
                nzb_link = ""
                message_id = ""
                if nzb_elem:
                    nzb_link = nzb_elem.get("href", "")
                    # Extract message ID from URL
                    if "messageid=" in nzb_link:
                        message_id = urllib.parse.unquote(
                            nzb_link.split("messageid=")[1].split("&")[0]
                        )
                    if nzb_link and not nzb_link.startswith("http"):
                        nzb_link = BASE_URL + "/" + nzb_link.lstrip("/")
                
                # Extract file size from td.filesize
                size_elem = row.select_one("td.filesize")
                size_text = size_elem.text.strip() if size_elem else ""
                size_bytes = parse_size(size_text)
                
                # Extract date from td.date title attribute
                date_elem = row.select_one("td.date")
                pub_date = ""
                if date_elem:
                    date_title = date_elem.get("title", "")
                    # Format: "16/01/2026 (13:37:04)"
                    if date_title:
                        try:
                            date_match = re.match(r"(\d{2}/\d{2}/\d{4})\s*\((\d{2}:\d{2}:\d{2})\)", date_title)
                            if date_match:
                                dt = datetime.strptime(f"{date_match.group(1)} {date_match.group(2)}", "%d/%m/%Y %H:%M:%S")
                                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
                        except ValueError:
                            pass
                
                if not pub_date:
                    pub_date = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
                
                # Extract category from td.category
                cat_elem = row.select_one("td.category a")
                category_name = cat_elem.text.strip() if cat_elem else ""
                
                # Extract genre
                genre_elem = row.select_one("td.genre a")
                genre = genre_elem.text.strip() if genre_elem else ""
                
                # Determine Newznab category
                newznab_cat = parse_clubnzb_category(row_classes)
                
                # Generate unique ID
                guid = generate_guid(message_id or title)
                
                results.append({
                    "title": title,
                    "guid": guid,
                    "link": nzb_link,
                    "size": size_bytes,
                    "pub_date": pub_date,
                    "category": newznab_cat,
                    "category_name": category_name,
                    "genre": genre,
                    "detail_link": detail_link,
                    "message_id": message_id,
                })
                
            except Exception as e:
                print(f"[ClubNZB] Error parsing row: {e}")
                continue
    
    return results


def escape_xml(text: str) -> str:
    """Escape special XML characters"""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_newznab_xml(results: list[dict], offset: int = 0, total: int = 0) -> str:
    """Build Newznab-compatible XML response"""
    
    xml_items = []
    for item in results:
        xml_items.append(f"""
    <item>
      <title>{escape_xml(item['title'])}</title>
      <guid isPermaLink="true">{escape_xml(item['guid'])}</guid>
      <link>{escape_xml(item['link'])}</link>
      <comments>{escape_xml(item.get('detail_link', ''))}</comments>
      <pubDate>{item['pub_date']}</pubDate>
      <category>{escape_xml(item.get('category_name', 'TV'))}</category>
      <description>{escape_xml(item.get('genre', ''))}</description>
      <enclosure url="{escape_xml(item['link'])}" length="{item['size']}" type="application/x-nzb" />
      <newznab:attr name="guid" value="{escape_xml(item['guid'])}" />
      <newznab:attr name="size" value="{item['size']}" />
      <newznab:attr name="category" value="{item.get('category', '5000')}" />
      <newznab:attr name="grabs" value="0" />
    </item>""")
    
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
  <channel>
    <title>ClubNZB Proxy</title>
    <description>Newznab API proxy for clubnzb.com</description>
    <link>{BASE_URL}</link>
    <language>nl</language>
    <newznab:response offset="{offset}" total="{total or len(results)}" />
{"".join(xml_items)}
  </channel>
</rss>"""


def build_caps_xml() -> str:
    """Build capabilities XML for Prowlarr"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="ClubNZB Proxy" strapline="Newznab API proxy for clubnzb.com" 
          url="{BASE_URL}" email="" />
  <limits max="100" default="100" />
  <retention days="3000" />
  <registration available="no" open="no" />
  <searching>
    <search available="yes" supportedParams="q" />
    <tv-search available="yes" supportedParams="q,season,ep" />
    <movie-search available="yes" supportedParams="q" />
    <audio-search available="no" supportedParams="" />
    <book-search available="no" supportedParams="" />
  </searching>
  <categories>
    <category id="2000" name="Movies">
      <subcat id="2010" name="Movies/Foreign" />
      <subcat id="2020" name="Movies/Other" />
      <subcat id="2030" name="Movies/SD" />
      <subcat id="2040" name="Movies/HD" />
      <subcat id="2045" name="Movies/UHD" />
      <subcat id="2050" name="Movies/BluRay" />
    </category>
    <category id="5000" name="TV">
      <subcat id="5020" name="TV/Foreign" />
      <subcat id="5030" name="TV/SD" />
      <subcat id="5040" name="TV/HD" />
      <subcat id="5045" name="TV/UHD" />
      <subcat id="5080" name="TV/Documentary" />
    </category>
  </categories>
</caps>"""


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "ClubNZB Proxy", "version": "1.0.0"}


@app.get("/api")
async def api_endpoint(
    t: str = Query(..., description="API function"),
    q: Optional[str] = Query(None, description="Search query"),
    apikey: Optional[str] = Query(None, description="API key (ignored)"),
    cat: Optional[str] = Query(None, description="Category"),
    season: Optional[str] = Query(None, description="Season number"),
    ep: Optional[str] = Query(None, description="Episode number"),
    imdbid: Optional[str] = Query(None, description="IMDB ID"),
    offset: int = Query(0, description="Result offset"),
    limit: int = Query(100, description="Result limit"),
    extended: Optional[str] = Query(None, description="Extended attributes"),
):
    """
    Newznab API endpoint
    Supported functions: caps, search, tvsearch, movie
    """
    
    # Return capabilities
    if t == "caps":
        return Response(content=build_caps_xml(), media_type="application/xml")
    
    # Handle search requests
    if t in ("search", "tvsearch", "movie", "tv"):
        search_query = q or ""
        
        # For TV search, append season/episode to query
        if t in ("tvsearch", "tv") and search_query:
            if season:
                search_query += f" S{season.zfill(2)}"
            if ep:
                search_query += f"E{ep.zfill(2)}"
        
        # Determine category
        category = None
        if cat:
            # Take first category if multiple provided
            category = cat.split(",")[0]
        elif t == "movie":
            category = "2000"
        elif t in ("tvsearch", "tv"):
            category = "5000"
        
        # If no query, return empty results (Prowlarr test)
        if not search_query:
            # Return a simple test search with a common term
            search_query = "the"
        
        results = await search_clubnzb(search_query, category)
        
        # Apply offset and limit
        total = len(results)
        results = results[offset:offset + limit]
        
        return Response(
            content=build_newznab_xml(results, offset, total),
            media_type="application/xml"
        )
    
    # Unknown function
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><error code="202" description="No such function" />',
        media_type="application/xml",
        status_code=400
    )


@app.get("/getnzb")
async def get_nzb(messageid: str):
    """Proxy NZB download from clubnzb.com"""
    nzb_url = f"{BASE_URL}/?page=getnzb&action=display&messageid={urllib.parse.quote(messageid)}"
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        headers = {"User-Agent": USER_AGENT}
        response = await client.get(nzb_url, headers=headers)
        
        return Response(
            content=response.content,
            media_type="application/x-nzb",
            headers={"Content-Disposition": f'attachment; filename="{messageid}.nzb"'}
        )


@app.get("/health")
async def health():
    """Health check for Docker"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5080)
