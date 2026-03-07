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

app = FastAPI(title="ClubNZB Proxy", version="1.0.0")

BASE_URL = "https://www.clubnzb.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


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


def detect_category_from_classes(row_classes: str) -> str:
    """Detect Newznab category from Spotweb row classes"""
    classes = row_classes.lower()
    
    # Check for specific sub-categories
    if "spotcat0_z0" in classes:
        return "2000"  # Movies
    if "spotcat0_z1" in classes:
        return "5000"  # TV Series
    if "spotcat0_z2" in classes:
        return "7000"  # Books
    if "spotcat0_z3" in classes:
        return "5000"  # This seems to contain Dutch TV shows too
    if "spotcat1" in classes:
        return "3000"  # Music
    if "spotcat2" in classes:
        return "4000"  # Games
    if "spotcat3" in classes:
        return "4000"  # Applications
    if "spotcat0" in classes:
        return "2000"  # Default Image to Movies
    
    return "5000"  # Default to TV


async def search_clubnzb(query: str, category: Optional[str] = None) -> list[dict]:
    """
    Search clubnzb.com and return parsed results
    """
    results = []
    
    # Build search URL - use unfiltered search for best results
    # This searches across all categories, which works better for Dutch content
    search_url = (
        f"{BASE_URL}/?"
        f"search[value][]=Title:=:DEF:{urllib.parse.quote(query)}"
        f"&search[unfiltered]=true"  # Important: search across all categories
        f"&sortby=stamp"
        f"&sortdir=DESC"
    )
    
    print(f"[ClubNZB] Searching: {search_url}")
    print(f"[ClubNZB] Query: '{query}', Requested category: {category}")
    
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
        
        print(f"[ClubNZB] Found {len(rows)} rows in HTML")
        
        for row in rows:
            try:
                # Get row classes for category detection
                row_classes = " ".join(row.get("class", []))
                
                # Extract title from td.title a.spotlink
                title_elem = row.select_one("td.title a.spotlink")
                if not title_elem:
                    print(f"[ClubNZB] Row skipped: no title element")
                    continue
                
                # Get title from title attribute or text content
                title = title_elem.get("title") or title_elem.text.strip()
                if not title:
                    print(f"[ClubNZB] Row skipped: empty title")
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
                    if "messageid=" in nzb_link:
                        message_id = urllib.parse.unquote(
                            nzb_link.split("messageid=")[1].split("&")[0]
                        )
                    if nzb_link and not nzb_link.startswith("http"):
                        nzb_link = BASE_URL + "/" + nzb_link.lstrip("/")
                
                if not nzb_link:
                    print(f"[ClubNZB] Row skipped: no NZB link for '{title[:50]}'")
                    continue
                
                # Extract file size from td.filesize
                size_elem = row.select_one("td.filesize")
                size_text = size_elem.text.strip() if size_elem else ""
                size_bytes = parse_size(size_text)
                
                # Extract date from td.date title attribute
                date_elem = row.select_one("td.date")
                pub_date = ""
                if date_elem:
                    date_title = date_elem.get("title", "")
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
                
                # Extract category name from td.category
                cat_elem = row.select_one("td.category a")
                category_name = cat_elem.text.strip() if cat_elem else ""
                
                # Detect category from row classes, or use requested category
                detected_cat = detect_category_from_classes(row_classes)
                
                # If a specific category was requested, use it; otherwise use detected
                if category:
                    newznab_cat = category
                else:
                    newznab_cat = detected_cat
                
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
                    "detail_link": detail_link,
                    "message_id": message_id,
                })
                
            except Exception as e:
                print(f"[ClubNZB] Error parsing row: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    print(f"[ClubNZB] Returning {len(results)} results")
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
        cat_id = item.get('category', '5000')
        xml_items.append(f"""
    <item>
      <title>{escape_xml(item['title'])}</title>
      <guid isPermaLink="true">{escape_xml(item['guid'])}</guid>
      <link>{escape_xml(item['link'])}</link>
      <comments>{escape_xml(item.get('detail_link', ''))}</comments>
      <pubDate>{item['pub_date']}</pubDate>
      <category>{cat_id}</category>
      <enclosure url="{escape_xml(item['link'])}" length="{item['size']}" type="application/x-nzb" />
      <newznab:attr name="category" value="{cat_id}" />
      <newznab:attr name="size" value="{item['size']}" />
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
        
        # Determine the category to tag results with
        category = None
        if cat:
            first_cat = cat.split(",")[0]
            if first_cat.startswith("2"):
                category = "2000"
            elif first_cat.startswith("5"):
                category = "5000"
        elif t == "movie":
            category = "2000"
        elif t in ("tvsearch", "tv"):
            category = "5000"
        
        # If no query, do a generic search
        if not search_query:
            search_query = "2026"  # Search for recent content
        
        # For TV search, try BOTH approaches:
        # 1. Search with just the show name (broader, catches different season numbering)
        # 2. If season/ep provided, also try with S##E## (for exact matches)
        all_results = []
        seen_guids = set()
        
        # First search: just the show name
        print(f"[ClubNZB] Search 1: Show name only '{search_query}'")
        results1 = await search_clubnzb(search_query, category)
        for r in results1:
            if r['guid'] not in seen_guids:
                all_results.append(r)
                seen_guids.add(r['guid'])
        
        # Second search: with S##E## if provided (for TV searches)
        if t in ("tvsearch", "tv") and search_query and (season or ep):
            specific_query = search_query
            if season:
                specific_query += f" S{season.zfill(2)}"
            if ep:
                specific_query += f"E{ep.zfill(2)}"
            
            print(f"[ClubNZB] Search 2: With S##E## '{specific_query}'")
            results2 = await search_clubnzb(specific_query, category)
            for r in results2:
                if r['guid'] not in seen_guids:
                    all_results.append(r)
                    seen_guids.add(r['guid'])
        
        print(f"[ClubNZB] Combined unique results: {len(all_results)}")
        
        # Apply offset and limit
        total = len(all_results)
        all_results = all_results[offset:offset + limit]
        
        return Response(
            content=build_newznab_xml(all_results, offset, total),
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
