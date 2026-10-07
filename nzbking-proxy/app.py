"""
NZBKing Proxy - Newznab API wrapper for nzbking.com
Allows Prowlarr/Radarr/Sonarr to search nzbking.com
"""

import hashlib
import html
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, Response

app = FastAPI(title="NZBKing Proxy", version="1.0.0")

BASE_URL = "https://nzbking.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def generate_guid(message_id: str) -> str:
    """Generate a unique GUID from message ID"""
    return hashlib.md5(message_id.encode()).hexdigest()


def parse_size(size_str: str) -> int:
    """Convert size string like '469MB' or '1 GB' to bytes"""
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


def parse_age_to_date(age_str: str) -> str:
    """Convert an nzbking age token like '3874d' / '12h' / '5m' to an RFC822 pubDate"""
    now = datetime.utcnow()
    match = re.match(r"(\d+)\s*([dhm])", age_str.strip().lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            now = now - timedelta(days=amount)
        elif unit == "h":
            now = now - timedelta(hours=amount)
        elif unit == "m":
            now = now - timedelta(minutes=amount)
    return now.strftime("%a, %d %b %Y %H:%M:%S +0000")


def clean_subject(subject: str) -> str:
    """Normalize a raw usenet subject into a release title.

    Keeps the bulk of the subject (Radarr/Sonarr parse it well) but trims the
    yEnc/part-counter noise so matching is cleaner.
    """
    title = html.unescape(subject or "").strip()
    # Drop trailing yEnc marker and any "(1/1)" style part counters at the end
    title = re.sub(r"\s*yEnc\b.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\(\d+/\d+\)\s*$", "", title)
    # Collapse whitespace
    title = re.sub(r"\s+", " ", title).strip()
    return title


def extract_subject_text(subject_div) -> str:
    """Pull the leading subject text from a search-subject div (text before the buttons/<br>)."""
    parts = []
    for child in subject_div.children:
        name = getattr(child, "name", None)
        if name in ("br", "a", "span", "div"):
            break
        text = child.get_text() if hasattr(child, "get_text") else str(child)
        if text and text.strip():
            parts.append(text.strip())
    return " ".join(parts).strip()


async def search_nzbking(query: str, category: Optional[str] = None) -> list[dict]:
    """
    Search nzbking.com and return parsed results
    """
    results = []

    search_url = (
        f"{BASE_URL}/search/?"
        f"q={urllib.parse.quote(query)}"
        f"&so=m"  # Magic (relevance) sort
    )

    print(f"[NZBKing] Searching: {search_url}")
    print(f"[NZBKing] Query: '{query}', Requested category: {category}")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        headers = {"User-Agent": USER_AGENT}

        try:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as e:
            print(f"[NZBKing] Error fetching search results: {e}")
            return results

        soup = BeautifulSoup(response.text, "lxml")

        rows = soup.select("div.search-result")
        print(f"[NZBKing] Found {len(rows)} result rows in HTML")

        for row in rows:
            try:
                # Skip the header row (has *-hdr children, no checkbox)
                checkbox = row.select_one("div.search-select input[name='nzb']")
                if not checkbox:
                    continue

                message_id = checkbox.get("value", "").strip()
                if not message_id:
                    continue

                subject_div = row.select_one("div.search-subject")
                if not subject_div:
                    continue

                raw_subject = extract_subject_text(subject_div)
                title = clean_subject(raw_subject)
                if not title:
                    continue

                # Size lives inline in the subject div text as "size: 469MB"
                subject_text = subject_div.get_text(" ", strip=True)
                size_bytes = 0
                size_match = re.search(r"size:\s*([\d.]+\s*[KMGT]?B)", subject_text, re.IGNORECASE)
                if size_match:
                    size_bytes = parse_size(size_match.group(1))

                nzb_link = f"{BASE_URL}/nzb:{message_id}/"
                detail_link = f"{BASE_URL}/details:{message_id}/"

                age_elem = row.select_one("div.search-age")
                age_text = age_elem.get_text(strip=True) if age_elem else ""
                pub_date = parse_age_to_date(age_text)

                poster_elem = row.select_one("div.search-poster a")
                poster = poster_elem.get_text(strip=True) if poster_elem else ""

                group_elem = row.select_one("div.search-groups")
                category_name = group_elem.get_text(" ", strip=True) if group_elem else ""

                newznab_cat = category or "5000"

                guid = generate_guid(message_id)

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
                    "poster": poster,
                })

            except Exception as e:
                print(f"[NZBKing] Error parsing row: {e}")
                import traceback
                traceback.print_exc()
                continue

    print(f"[NZBKing] Returning {len(results)} results")
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
    <title>NZBKing Proxy</title>
    <description>Newznab API proxy for nzbking.com</description>
    <link>{BASE_URL}</link>
    <language>en</language>
    <newznab:response offset="{offset}" total="{total or len(results)}" />
{"".join(xml_items)}
  </channel>
</rss>"""


def build_caps_xml() -> str:
    """Build capabilities XML for Prowlarr"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="NZBKing Proxy" strapline="Newznab API proxy for nzbking.com"
          url="{BASE_URL}" email="" />
  <limits max="100" default="100" />
  <retention days="6000" />
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
    return {"status": "ok", "service": "NZBKing Proxy", "version": "1.0.0"}


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

    if t == "caps":
        return Response(content=build_caps_xml(), media_type="application/xml")

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

        if not search_query:
            search_query = "2026"  # Search for recent content

        all_results = []
        seen_guids = set()

        # First search: just the show/movie name
        print(f"[NZBKing] Search 1: name only '{search_query}'")
        results1 = await search_nzbking(search_query, category)
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

            print(f"[NZBKing] Search 2: With S##E## '{specific_query}'")
            results2 = await search_nzbking(specific_query, category)
            for r in results2:
                if r['guid'] not in seen_guids:
                    all_results.append(r)
                    seen_guids.add(r['guid'])

        print(f"[NZBKing] Combined unique results: {len(all_results)}")

        # Prowlarr/Radarr/Sonarr sometimes send limit=0 meaning "use default".
        # Treat any non-positive limit as the default page size.
        effective_limit = limit if limit > 0 else 100

        total = len(all_results)
        all_results = all_results[offset:offset + effective_limit]

        return Response(
            content=build_newznab_xml(all_results, offset, total),
            media_type="application/xml"
        )

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><error code="202" description="No such function" />',
        media_type="application/xml",
        status_code=400
    )


@app.get("/getnzb")
async def get_nzb(id: str):
    """Proxy NZB download from nzbking.com"""
    nzb_url = f"{BASE_URL}/nzb:{urllib.parse.quote(id)}/"

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        headers = {"User-Agent": USER_AGENT}
        response = await client.get(nzb_url, headers=headers)

        return Response(
            content=response.content,
            media_type="application/x-nzb",
            headers={"Content-Disposition": f'attachment; filename="{id}.nzb"'}
        )


@app.get("/health")
async def health():
    """Health check for Docker"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5081)
