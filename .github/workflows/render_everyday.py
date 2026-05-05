#!/usr/bin/env python3
"""SAS EuroBonus Everyday tracker — renderer for the in-person/onsite UI.

Reads per-country JSON from data/everyday/{cc}/shops.json (produced by
scrape_everyday.py) and writes docs/everyday.html — a standalone page with
embedded data, styling, and client-side rendering.

Visual language matches docs/index.html (CSS vars, sticky header, card
geometry, modal pattern). Stage 5 will merge the two pages behind a single
tab toggle.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "everyday"
HTML_FILE = REPO_ROOT / "docs" / "everyday.html"

CLOUDFLARE_TOKEN = "c0d97a34f9524bd18f638693155d6704"

# Faroes uses Danish per the spec (Faroese mostly speak Danish).
COUNTRIES = [
    {"code": "SE", "local_lang": "sv", "name": "Sverige", "languages": ["sv", "en"]},
    {"code": "DK", "local_lang": "da", "name": "Danmark", "languages": ["da", "en"]},
    {"code": "NO", "local_lang": "nb", "name": "Norge",   "languages": ["nb", "en"]},
    {"code": "FI", "local_lang": "en", "name": "Suomi",   "languages": ["en"]},
    {"code": "FO", "local_lang": "da", "name": "Føroyar", "languages": ["da", "en"]},
]

STRINGS = {
    "sv": {
        "title": "EuroBonus Everyday",
        "tagline": "Butiker och restauranger som ger EuroBonus-poäng när du betalar med ett kopplat kort.",
        "tab_online": "Online", "tab_everyday": "I butik",
        "filter_all": "Alla", "filter_onsite": "I butik", "filter_online": "Online",
        "search_placeholder": "Sök butik, stad eller adress…",
        "meta_template": "{shops} ställen · {onsite} i butik · {online} online · uppdaterad {ts}",
        "dark_mode": "Dark mode", "light_mode": "Light mode",
        "no_shops": "Inga ställen matchar.",
        "online_only": "Online", "points_per_100": "p / 100 kr",
        "modal_visit": "Öppna webbplats", "modal_directions": "Vägbeskrivning",
        "modal_close": "Stäng", "modal_phone": "Telefon", "modal_cards": "Betalkort",
        "modal_address": "Adress", "modal_campaign": "Kampanj",
        "footer_unaffiliated": "Oberoende sida, inte ansluten till SAS eller EuroBonus.",
        "footer_about": "Om sidan", "footer_privacy": "Integritet",
    },
    "en": {
        "title": "EuroBonus Everyday",
        "tagline": "Shops and restaurants that earn EuroBonus points when you pay with a linked card.",
        "tab_online": "Online", "tab_everyday": "In store",
        "filter_all": "All", "filter_onsite": "In store", "filter_online": "Online",
        "search_placeholder": "Search shop, city, or address…",
        "meta_template": "{shops} places · {onsite} in store · {online} online · updated {ts}",
        "dark_mode": "Dark mode", "light_mode": "Light mode",
        "no_shops": "No places match.",
        "online_only": "Online", "points_per_100": "p / 100",
        "modal_visit": "Open website", "modal_directions": "Directions",
        "modal_close": "Close", "modal_phone": "Phone", "modal_cards": "Cards",
        "modal_address": "Address", "modal_campaign": "Campaign",
        "footer_unaffiliated": "Independent site, not affiliated with SAS or EuroBonus.",
        "footer_about": "About", "footer_privacy": "Privacy",
    },
    "da": {
        "title": "EuroBonus Everyday",
        "tagline": "Butikker og restauranter, der giver EuroBonus-point, når du betaler med et tilknyttet kort.",
        "tab_online": "Online", "tab_everyday": "I butik",
        "filter_all": "Alle", "filter_onsite": "I butik", "filter_online": "Online",
        "search_placeholder": "Søg butik, by eller adresse…",
        "meta_template": "{shops} steder · {onsite} i butik · {online} online · opdateret {ts}",
        "dark_mode": "Dark mode", "light_mode": "Light mode",
        "no_shops": "Ingen steder matcher.",
        "online_only": "Online", "points_per_100": "p / 100 kr",
        "modal_visit": "Åbn hjemmeside", "modal_directions": "Rutevejledning",
        "modal_close": "Luk", "modal_phone": "Telefon", "modal_cards": "Betalingskort",
        "modal_address": "Adresse", "modal_campaign": "Kampagne",
        "footer_unaffiliated": "Uafhængig side, ikke tilknyttet SAS eller EuroBonus.",
        "footer_about": "Om", "footer_privacy": "Privatliv",
    },
    "nb": {
        "title": "EuroBonus Everyday",
        "tagline": "Butikker og restauranter som gir EuroBonus-poeng når du betaler med et tilknyttet kort.",
        "tab_online": "Online", "tab_everyday": "I butikk",
        "filter_all": "Alle", "filter_onsite": "I butikk", "filter_online": "Online",
        "search_placeholder": "Søk butikk, by eller adresse…",
        "meta_template": "{shops} steder · {onsite} i butikk · {online} online · oppdatert {ts}",
        "dark_mode": "Dark mode", "light_mode": "Light mode",
        "no_shops": "Ingen steder matcher.",
        "online_only": "Online", "points_per_100": "p / 100 kr",
        "modal_visit": "Åpne nettside", "modal_directions": "Veibeskrivelse",
        "modal_close": "Lukk", "modal_phone": "Telefon", "modal_cards": "Betalingskort",
        "modal_address": "Adresse", "modal_campaign": "Kampanje",
        "footer_unaffiliated": "Uavhengig side, ikke tilknyttet SAS eller EuroBonus.",
        "footer_about": "Om", "footer_privacy": "Personvern",
    },
}

# Defensive markdown unwrap — scraper should already do this, but the API
# has been known to return [text](url) for some entries (Faroese hotels,
# some Brasilia branches in NO).
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|www\.[^)\s]+)\)")


def unwrap_md(value):
    if not value:
        return ""
    text = value.strip()
    m = _MARKDOWN_LINK_RE.search(text)
    return m.group(2).strip() if m else text


def normalize_url(value):
    """Ensure URL has a scheme so anchor hrefs work."""
    v = unwrap_md(value)
    if not v:
        return ""
    if v.startswith(("http://", "https://")):
        return v
    if v.startswith("www."):
        return "https://" + v
    return "https://" + v  # last-resort prepend


def maps_url(shop):
    """Google Maps URL — coords if we have them, else address search."""
    if shop.get("lat") is not None and shop.get("lng") is not None:
        return f"https://www.google.com/maps/search/?api=1&query={shop['lat']},{shop['lng']}"
    parts = [shop.get("name"), shop.get("address"), shop.get("city"), shop.get("postcode")]
    parts = [p for p in parts if p and p != "."]
    if not parts:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=" + quote(", ".join(parts))


def area_label(shop):
    """One-line eyebrow text for the card top: city, or 'Online' for webshops."""
    if shop.get("mode") == "online":
        return None  # rendered as a chip in JS instead
    city = (shop.get("city") or "").strip()
    if city and city != ".":
        return city
    return ""


def load_country(code):
    path = DATA_DIR / code.lower() / "shops.json"
    if not path.exists():
        return {"shops": [], "updated": None}
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_dataset(country_code):
    raw = load_country(country_code)
    shops_out = []
    for s in raw.get("shops", []):
        if s.get("status") != "active":
            continue
        shops_out.append({
            "uuid": s.get("uuid"),
            "name": s.get("name"),
            "city": (s.get("city") or "").strip() if (s.get("city") or "").strip() != "." else "",
            "area": area_label(s),
            "address": (s.get("address") or "").strip() if (s.get("address") or "").strip() != "." else "",
            "postcode": (s.get("postcode") or "").strip() if (s.get("postcode") or "").strip() != "." else "",
            "lat": s.get("lat"),
            "lng": s.get("lng"),
            "mode": s.get("mode") or "onsite",
            "points": s.get("points_per_100") or 0,
            "currency": s.get("currency") or "",
            "website": normalize_url(s.get("website")),
            "phone": (s.get("phone") or "").strip(),
            "description": s.get("description") or "",
            "cards_accepted": s.get("cards_accepted") or [],
            "has_campaign": bool(s.get("has_campaign")),
            "campaign_title": s.get("campaign_title"),
            "campaign_description": s.get("campaign_description"),
            "maps_url": maps_url(s),
        })
    shops_out.sort(key=lambda s: (s["name"] or "").lower())
    onsite = sum(1 for s in shops_out if s["mode"] == "onsite")
    online = sum(1 for s in shops_out if s["mode"] == "online")
    return {
        "shops": shops_out,
        "onsite_count": onsite,
        "online_count": online,
        "updated": raw.get("updated"),
    }


def render_html(datasets):
    payload = {
        "datasets": json.dumps(datasets, ensure_ascii=False),
        "strings": json.dumps(STRINGS, ensure_ascii=False),
        "countries": json.dumps(COUNTRIES, ensure_ascii=False),
        "default_country": "SE",
        "default_lang": "sv",
        "cf_token": CLOUDFLARE_TOKEN,
    }
    return _HTML_TEMPLATE.format(**payload)


# Raw string: regex escapes (\b, \d, \w, \s) ship to the JS untouched.
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="description" content="SAS EuroBonus Everyday — butiker och restauranger i Norden där du tjänar EuroBonus-poäng när du betalar med kopplat kort.">
<meta property="og:title" content="EuroBonus Everyday — butiker och restauranger">
<meta property="og:description" content="Översikt över SAS EuroBonus Everyday-partners i Norden. Tjäna poäng när du handlar i butik eller på restaurang.">
<meta property="og:type" content="website">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>EuroBonus Everyday</title>
<style>
:root {{
  --bg: #faf9f7; --surface: #ffffff;
  --border: rgba(0, 0, 0, 0.08); --border-strong: rgba(0, 0, 0, 0.16);
  --text: #1a1a1a; --text-muted: #595959; --text-faint: #707070;
  --accent: #1858c7; --accent-bg: rgba(24, 88, 199, 0.08);
  --warn: #b85c00;
  --shadow-sticky: 0 4px 12px rgba(0, 0, 0, 0.06);
}}
html[data-theme="dark"] {{
  --bg: #0f0f10; --surface: #1a1a1c;
  --border: rgba(255, 255, 255, 0.08); --border-strong: rgba(255, 255, 255, 0.18);
  --text: #ededed; --text-muted: #b3b3b3; --text-faint: #8a8a8a;
  --accent: #6ea8ff; --accent-bg: rgba(110, 168, 255, 0.14);
  --warn: #f0a66c;
  --shadow-sticky: 0 4px 16px rgba(0, 0, 0, 0.4);
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--text);
  margin: 0; padding: 0 0 64px;
  font-size: 14px; line-height: 1.5;
}}
.sas-container {{ max-width: 1500px; margin: 0 auto; padding: 0 24px; }}

.sas-sticky-wrap {{ background: var(--bg); transition: box-shadow 0.2s ease, border-color 0.2s ease, padding-top 0.2s ease, padding-bottom 0.2s ease; padding-top: 32px; }}
.sas-sticky-wrap.is-stuck {{ box-shadow: var(--shadow-sticky); border-bottom: 0.5px solid var(--border); padding-top: 16px; padding-bottom: 8px; }}
@media (min-width: 641px) {{
  .sas-sticky-wrap {{ position: sticky; top: 0; z-index: 50; }}
}}

.sas-header {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 18px; gap: 24px; flex-wrap: wrap; transition: margin-bottom 0.2s ease; }}
.sas-sticky-wrap.is-stuck .sas-header {{ margin-bottom: 10px; }}
.sas-title {{ font-size: 28px; font-weight: 500; letter-spacing: -0.02em; margin: 0 0 4px 0; transition: font-size 0.2s ease; }}
.sas-sticky-wrap.is-stuck .sas-title {{ font-size: 20px; }}
.sas-tagline {{ font-size: 14px; color: var(--text-muted); max-height: 60px; opacity: 1; overflow: hidden; transition: max-height 0.2s ease, opacity 0.2s ease, margin 0.2s ease; max-width: 640px; }}
.sas-sticky-wrap.is-stuck .sas-tagline {{ max-height: 0; opacity: 0; margin: 0; }}
.sas-meta {{ font-size: 13px; color: var(--text-faint); font-family: ui-monospace, "SF Mono", Menlo, monospace; margin-top: 6px; }}
.sas-sticky-wrap.is-stuck .sas-meta {{ display: none; }}

.sas-header-controls {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.sas-header-select {{ font-family: inherit; font-size: 13px; padding: 7px 12px; border: 0.5px solid var(--border-strong); border-radius: 999px; background: var(--surface); color: var(--text); cursor: pointer; }}
.sas-toggle {{ background: none; border: 0.5px solid var(--border-strong); color: var(--text-muted); padding: 7px 14px; border-radius: 999px; font-size: 13px; cursor: pointer; font-family: inherit; }}
.sas-toggle:hover {{ color: var(--text); }}

.sas-tabs {{ display: inline-flex; gap: 0; border: 0.5px solid var(--border-strong); border-radius: 999px; padding: 3px; background: var(--surface); margin-bottom: 14px; }}
.sas-tab {{ font-family: inherit; font-size: 13px; padding: 6px 14px; border: 0; border-radius: 999px; background: transparent; color: var(--text-muted); cursor: pointer; text-decoration: none; }}
.sas-tab:hover {{ color: var(--text); }}
.sas-tab.active {{ background: var(--accent); color: #fff; }}

.sas-filter-row {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }}
.sas-chip {{ font-size: 14px; padding: 8px 16px; border: 0.5px solid var(--border); border-radius: 999px; background: transparent; color: var(--text-muted); cursor: pointer; font-family: inherit; white-space: nowrap; }}
.sas-chip:hover {{ color: var(--text); }}
.sas-chip.active {{ background: var(--surface); color: var(--text); border-color: var(--border-strong); }}

.sas-search {{ width: 100%; font-size: 16px; padding: 13px 18px; border: 0.5px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text); font-family: inherit; margin-bottom: 24px; }}
.sas-sticky-wrap.is-stuck .sas-search {{ margin-bottom: 0; padding: 10px 14px; font-size: 14px; }}
.sas-search:focus {{ outline: none; border-color: var(--border-strong); }}

.sas-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; min-height: 60vh; }}
@media (min-width: 1100px) {{
  .sas-grid {{ grid-template-columns: repeat(4, 1fr); }}
}}

.sas-card {{ background: var(--surface); border: 0.5px solid var(--border); border-radius: 12px; padding: 18px 20px; display: flex; flex-direction: column; gap: 12px; min-height: 200px; color: inherit; transition: border-color 0.12s, transform 0.12s; cursor: pointer; }}
.sas-card:hover {{ border-color: var(--border-strong); transform: translateY(-1px); }}
.sas-card.campaign {{ border-color: var(--accent); }}

.sas-eyebrow {{ font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-faint); display: flex; align-items: center; gap: 8px; }}
.sas-eyebrow-tag {{ background: var(--accent-bg); color: var(--accent); padding: 2px 8px; border-radius: 999px; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 10px; letter-spacing: 0.04em; }}
.sas-card-name {{ font-size: 17px; font-weight: 500; line-height: 1.25; margin: 0; }}
.sas-card-address {{ font-size: 13px; color: var(--text-muted); line-height: 1.4; }}

.sas-points-row {{ display: flex; align-items: baseline; gap: 6px; margin-top: auto; padding-top: 8px; }}
.sas-points-main {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 22px; font-weight: 500; letter-spacing: -0.02em; line-height: 1; }}
.sas-points-unit {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px; color: var(--text-faint); }}

.sas-card-actions {{ display: flex; gap: 8px; padding-top: 8px; border-top: 0.5px solid var(--border); }}
.sas-card-btn {{ flex: 1; font-family: inherit; font-size: 12px; font-weight: 500; padding: 8px 10px; border: 0.5px solid var(--border-strong); border-radius: 8px; background: transparent; color: var(--text); cursor: pointer; text-decoration: none; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; }}
.sas-card-btn:hover {{ background: var(--accent-bg); color: var(--accent); border-color: var(--accent); }}
.sas-card-btn[aria-disabled="true"] {{ opacity: 0.4; pointer-events: none; }}
.sas-card-btn svg {{ width: 12px; height: 12px; flex-shrink: 0; }}

.sas-hidden {{ display: none !important; }}
.sas-empty {{ color: var(--text-faint); font-size: 14px; padding: 16px 0; }}

.sas-modal-backdrop {{ position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45); z-index: 100; display: flex; align-items: flex-end; justify-content: center; opacity: 0; pointer-events: none; transition: opacity 0.2s ease; }}
.sas-modal-backdrop.open {{ opacity: 1; pointer-events: auto; }}
.sas-modal {{ background: var(--surface); width: 100%; max-width: 560px; border-radius: 20px 20px 0 0; max-height: 85vh; display: flex; flex-direction: column; transform: translateY(100%); transition: transform 0.25s ease; overflow: hidden; }}
.sas-modal-backdrop.open .sas-modal {{ transform: translateY(0); }}
.sas-modal-handle {{ width: 36px; height: 4px; border-radius: 2px; background: var(--border-strong); margin: 10px auto 0; flex-shrink: 0; }}
.sas-modal-body {{ overflow-y: auto; padding: 20px 24px 110px; flex: 1; }}
.sas-modal-eyebrow {{ font-size: 11px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }}
.sas-modal-title {{ font-size: 22px; font-weight: 500; letter-spacing: -0.01em; margin: 0 0 18px 0; }}
.sas-modal-stats {{ display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; background: var(--bg); border-radius: 10px; margin-bottom: 18px; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 13px; }}
.sas-modal-stat-row {{ display: flex; justify-content: space-between; gap: 12px; color: var(--text-muted); }}
.sas-modal-stat-row strong {{ color: var(--text); font-weight: 500; text-align: right; }}
.sas-modal-stat-row a {{ color: var(--accent); text-decoration: none; }}
.sas-modal-stat-row a:hover {{ text-decoration: underline; }}
.sas-modal-section-label {{ font-size: 11px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.08em; margin: 18px 0 6px; }}
.sas-modal-description {{ font-size: 14px; line-height: 1.6; color: var(--text-muted); }}
.sas-modal-description p {{ margin: 0 0 10px 0; }}
.sas-modal-description br + br {{ display: none; }}
.sas-modal-footer {{ position: absolute; bottom: 0; left: 0; right: 0; padding: 14px 20px calc(14px + env(safe-area-inset-bottom, 0px)); background: var(--surface); border-top: 0.5px solid var(--border); display: flex; gap: 10px; }}
.sas-modal-primary {{ flex: 1; background: var(--accent); color: #fff; padding: 13px; border: 0; border-radius: 10px; font-size: 14px; font-weight: 500; cursor: pointer; text-decoration: none; text-align: center; font-family: inherit; }}
.sas-modal-primary:hover {{ opacity: 0.9; }}
.sas-modal-secondary {{ flex: 1; background: transparent; color: var(--text); padding: 13px; border: 0.5px solid var(--border-strong); border-radius: 10px; font-size: 14px; font-weight: 500; cursor: pointer; text-decoration: none; text-align: center; font-family: inherit; }}
.sas-modal-secondary:hover {{ background: var(--accent-bg); color: var(--accent); border-color: var(--accent); }}
.sas-modal-close {{ background: none; border: 0.5px solid var(--border-strong); color: var(--text-muted); padding: 13px 16px; border-radius: 10px; font-size: 13px; cursor: pointer; font-family: inherit; }}
.sas-modal-close:hover {{ color: var(--text); }}

.sas-footer {{ display: flex; justify-content: space-between; align-items: center; margin-top: 64px; padding-top: 24px; border-top: 0.5px solid var(--border); gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--text-faint); }}
.sas-footer a {{ color: var(--text-muted); text-decoration: none; }}
.sas-footer a:hover {{ color: var(--text); text-decoration: underline; }}

@media (max-width: 640px) {{
  body {{ padding: 0 0 48px; }}
  .sas-container {{ padding: 0 14px; }}
  .sas-sticky-wrap {{ padding-top: 20px; }}
  .sas-card {{ padding: 16px; min-height: 180px; }}
  .sas-modal {{ max-height: 90vh; }}
  .sas-footer {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
}}
</style>
</head>
<body>
<div class="sas-sticky-wrap" id="sticky-wrap">
  <div class="sas-container">
    <div class="sas-tabs" role="tablist">
      <a class="sas-tab" id="tab-online" href="index.html" role="tab"></a>
      <button class="sas-tab active" id="tab-everyday" role="tab" aria-selected="true"></button>
    </div>
    <div class="sas-header">
      <div>
        <h1 class="sas-title" id="title-text">EuroBonus Everyday</h1>
        <div class="sas-tagline" id="tagline-text"></div>
        <div class="sas-meta" id="meta-text"></div>
      </div>
      <div class="sas-header-controls">
        <select class="sas-header-select" id="country-select" aria-label="Country"></select>
        <select class="sas-header-select" id="language-select" aria-label="Language"></select>
        <button class="sas-toggle" id="theme-toggle">Dark mode</button>
      </div>
    </div>
    <div class="sas-filter-row">
      <div id="mode-filters" style="display: flex; gap: 8px; flex-wrap: wrap;"></div>
    </div>
    <input class="sas-search" id="search-box" type="search">
  </div>
</div>

<main class="sas-container">
  <div class="sas-grid" id="shop-grid"></div>
  <div class="sas-empty sas-hidden" id="empty-state"></div>
</main>

<div class="sas-container">
  <footer class="sas-footer">
    <div><span id="footer-unaffiliated"></span></div>
    <div>
      <a href="about.html" id="footer-about">About</a> ·
      <a href="privacy.html" id="footer-privacy">Privacy</a> ·
      <span>© 2026 David Kifarkis</span>
    </div>
  </footer>
</div>

<div class="sas-modal-backdrop" id="modal-backdrop">
  <div class="sas-modal" id="modal">
    <div class="sas-modal-handle"></div>
    <div class="sas-modal-body" id="modal-body"></div>
    <div class="sas-modal-footer">
      <a class="sas-modal-primary" id="modal-visit-btn" target="_blank" rel="noopener"></a>
      <a class="sas-modal-secondary" id="modal-directions-btn" target="_blank" rel="noopener"></a>
      <button class="sas-modal-close" id="modal-close" aria-label="Close"></button>
    </div>
  </div>
</div>

<script id="sas-data" type="application/json">{datasets}</script>
<script id="sas-strings" type="application/json">{strings}</script>
<script id="sas-countries" type="application/json">{countries}</script>

<script>
(function() {{
  var DATA = JSON.parse(document.getElementById('sas-data').textContent);
  var STRINGS = JSON.parse(document.getElementById('sas-strings').textContent);
  var COUNTRIES = JSON.parse(document.getElementById('sas-countries').textContent);
  var DEFAULT_COUNTRY = '{default_country}';
  var DEFAULT_LANG = '{default_lang}';

  var params = new URLSearchParams(window.location.search);
  var country = (params.get('c') || DEFAULT_COUNTRY).toUpperCase();
  var lang = params.get('l') || DEFAULT_LANG;
  var countryDef = COUNTRIES.find(function(c) {{ return c.code === country; }}) || COUNTRIES[0];
  if (!countryDef) {{ countryDef = COUNTRIES[0]; country = countryDef.code; }}
  if (countryDef.languages.indexOf(lang) === -1) lang = countryDef.local_lang;

  var state = {{ mode: 'all', query: '' }};
  var shopsByUuid = {{}};

  var root = document.documentElement;
  var toggle = document.getElementById('theme-toggle');
  function prefersDark() {{ return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }}
  function isDark() {{
    var t = root.getAttribute('data-theme');
    return t === 'dark' || (t !== 'light' && prefersDark());
  }}
  try {{
    var stored = localStorage.getItem('sas-theme');
    if (stored === 'dark' || stored === 'light') root.setAttribute('data-theme', stored);
  }} catch (e) {{}}
  toggle.addEventListener('click', function() {{
    var next = isDark() ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try {{ localStorage.setItem('sas-theme', next); }} catch (e) {{}}
    setToggleLabel();
  }});

  function t(key) {{ return (STRINGS[lang] || STRINGS.en)[key] || key; }}
  function setToggleLabel() {{ toggle.textContent = isDark() ? t('light_mode') : t('dark_mode'); }}

  function escapeHtml(s) {{
    return (s == null ? '' : String(s)).replace(/[&<>"']/g, function(c) {{
      return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}}[c];
    }});
  }}

  function iconExt() {{
    return '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 3H4a1 1 0 00-1 1v8a1 1 0 001 1h8a1 1 0 001-1v-2"/><path d="M9 3h4v4M13 3L7 9"/></svg>';
  }}
  function iconMap() {{
    return '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 14s5-4 5-8a5 5 0 10-10 0c0 4 5 8 5 8z"/><circle cx="8" cy="6" r="2"/></svg>';
  }}

  function eyebrowText(shop) {{
    if (shop.mode === 'online') return t('online_only');
    return shop.area || shop.city || '';
  }}

  function addressLine(shop) {{
    if (shop.mode === 'online') return '';
    var bits = [];
    if (shop.address) bits.push(shop.address);
    if (shop.postcode || shop.city) {{
      var pc = [shop.postcode, shop.city].filter(Boolean).join(' ');
      if (pc) bits.push(pc);
    }}
    return bits.join(' · ');
  }}

  var backdrop = document.getElementById('modal-backdrop');
  var modalBody = document.getElementById('modal-body');
  var modalVisit = document.getElementById('modal-visit-btn');
  var modalDirections = document.getElementById('modal-directions-btn');
  var modalClose = document.getElementById('modal-close');

  function openModal(shop) {{
    var rows = [];
    rows.push('<div class="sas-modal-stat-row"><span>EB</span><strong>' + shop.points + ' ' + escapeHtml(t('points_per_100')) + '</strong></div>');
    if (shop.cards_accepted && shop.cards_accepted.length) {{
      rows.push('<div class="sas-modal-stat-row"><span>' + escapeHtml(t('modal_cards')) + '</span><strong>' + shop.cards_accepted.map(escapeHtml).join(' · ') + '</strong></div>');
    }}
    if (shop.phone) {{
      rows.push('<div class="sas-modal-stat-row"><span>' + escapeHtml(t('modal_phone')) + '</span><strong><a href="tel:' + encodeURIComponent(shop.phone) + '">' + escapeHtml(shop.phone) + '</a></strong></div>');
    }}
    var addr = addressLine(shop);
    if (addr) {{
      rows.push('<div class="sas-modal-stat-row"><span>' + escapeHtml(t('modal_address')) + '</span><strong>' + escapeHtml(addr) + '</strong></div>');
    }}

    var html = '<div class="sas-modal-eyebrow">' + escapeHtml(eyebrowText(shop)) + '</div>' +
      '<h2 class="sas-modal-title">' + escapeHtml(shop.name) + '</h2>' +
      '<div class="sas-modal-stats">' + rows.join('') + '</div>';

    if (shop.has_campaign && (shop.campaign_title || shop.campaign_description)) {{
      html += '<div class="sas-modal-section-label">' + escapeHtml(t('modal_campaign')) + '</div>';
      if (shop.campaign_title) html += '<div class="sas-modal-description"><strong>' + escapeHtml(shop.campaign_title) + '</strong></div>';
      if (shop.campaign_description) html += '<div class="sas-modal-description">' + shop.campaign_description + '</div>';
    }}

    if (shop.description) {{
      html += '<div class="sas-modal-description" style="margin-top: 16px;">' + shop.description + '</div>';
    }}

    modalBody.innerHTML = html;

    if (shop.website) {{
      modalVisit.href = shop.website;
      modalVisit.textContent = t('modal_visit');
      modalVisit.style.display = '';
    }} else {{
      modalVisit.style.display = 'none';
    }}
    if (shop.maps_url && shop.mode !== 'online') {{
      modalDirections.href = shop.maps_url;
      modalDirections.textContent = t('modal_directions');
      modalDirections.style.display = '';
    }} else {{
      modalDirections.style.display = 'none';
    }}
    modalClose.textContent = t('modal_close');
    backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';
  }}

  function closeModal() {{
    backdrop.classList.remove('open');
    document.body.style.overflow = '';
  }}

  backdrop.addEventListener('click', function(e) {{ if (e.target === backdrop) closeModal(); }});
  modalClose.addEventListener('click', closeModal);
  document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});

  function cardHTML(shop) {{
    var div = document.createElement('div');
    div.className = 'sas-card' + (shop.has_campaign ? ' campaign' : '');
    div.dataset.uuid = shop.uuid;
    div.dataset.mode = shop.mode;
    var hay = [shop.name, shop.city, shop.address, shop.postcode].filter(Boolean).join(' ').toLowerCase();
    div.dataset.hay = hay;

    var addr = addressLine(shop);
    var unit = escapeHtml(t('points_per_100'));
    var actions = '';
    var visitBtn = shop.website
      ? '<a class="sas-card-btn" href="' + escapeHtml(shop.website) + '" target="_blank" rel="noopener" data-stop>' + iconExt() + '<span>' + escapeHtml(t('modal_visit')) + '</span></a>'
      : '<button class="sas-card-btn" aria-disabled="true">' + iconExt() + '<span>' + escapeHtml(t('modal_visit')) + '</span></button>';
    var mapsBtn = (shop.maps_url && shop.mode !== 'online')
      ? '<a class="sas-card-btn" href="' + escapeHtml(shop.maps_url) + '" target="_blank" rel="noopener" data-stop>' + iconMap() + '<span>' + escapeHtml(t('modal_directions')) + '</span></a>'
      : '<button class="sas-card-btn" aria-disabled="true">' + iconMap() + '<span>' + escapeHtml(t('modal_directions')) + '</span></button>';
    actions = '<div class="sas-card-actions">' + visitBtn + mapsBtn + '</div>';

    var eyebrow = '<div class="sas-eyebrow">' +
      (shop.mode === 'online'
        ? '<span class="sas-eyebrow-tag">' + escapeHtml(t('online_only')) + '</span>'
        : escapeHtml(eyebrowText(shop))) +
      '</div>';

    div.innerHTML =
      eyebrow +
      '<h2 class="sas-card-name">' + escapeHtml(shop.name) + '</h2>' +
      (addr ? '<div class="sas-card-address">' + escapeHtml(addr) + '</div>' : '') +
      '<div class="sas-points-row"><span class="sas-points-main">' + shop.points + '</span><span class="sas-points-unit">' + unit + '</span></div>' +
      actions;
    return div;
  }}

  function renderGrid() {{
    var ds = DATA[country] || {{ shops: [] }};
    var grid = document.getElementById('shop-grid');
    var empty = document.getElementById('empty-state');
    grid.innerHTML = '';

    var filtered = ds.shops.filter(function(s) {{
      if (state.mode !== 'all' && s.mode !== state.mode) return false;
      if (state.query && s.dataHay) return s.dataHay.indexOf(state.query) !== -1;
      return true;
    }});
    // Apply text query against precomputed haystack
    if (state.query) {{
      filtered = ds.shops.filter(function(s) {{
        if (state.mode !== 'all' && s.mode !== state.mode) return false;
        var hay = (s.name + ' ' + (s.city||'') + ' ' + (s.address||'') + ' ' + (s.postcode||'')).toLowerCase();
        return hay.indexOf(state.query) !== -1;
      }});
    }}

    if (!filtered.length) {{
      empty.classList.remove('sas-hidden');
      empty.textContent = t('no_shops');
    }} else {{
      empty.classList.add('sas-hidden');
    }}

    var frag = document.createDocumentFragment();
    filtered.forEach(function(s) {{
      shopsByUuid[s.uuid] = s;
      frag.appendChild(cardHTML(s));
    }});
    grid.appendChild(frag);
  }}

  function fmtTs(iso) {{
    if (!iso) return '';
    try {{
      var d = new Date(iso);
      return d.getUTCFullYear() + '-' +
        String(d.getUTCMonth() + 1).padStart(2, '0') + '-' +
        String(d.getUTCDate()).padStart(2, '0') + ' ' +
        String(d.getUTCHours()).padStart(2, '0') + ':' +
        String(d.getUTCMinutes()).padStart(2, '0') + ' UTC';
    }} catch (e) {{ return iso; }}
  }}

  function render() {{
    var ds = DATA[country] || {{ shops: [], onsite_count: 0, online_count: 0, updated: null }};
    document.getElementById('title-text').textContent = t('title');
    document.getElementById('tagline-text').textContent = t('tagline');
    document.getElementById('tab-online').textContent = t('tab_online');
    document.getElementById('tab-everyday').textContent = t('tab_everyday');
    document.getElementById('search-box').placeholder = t('search_placeholder');
    document.getElementById('footer-unaffiliated').textContent = t('footer_unaffiliated');
    document.getElementById('footer-about').textContent = t('footer_about');
    document.getElementById('footer-privacy').textContent = t('footer_privacy');

    var meta = t('meta_template')
      .replace('{{shops}}', ds.shops.length)
      .replace('{{onsite}}', ds.onsite_count || 0)
      .replace('{{online}}', ds.online_count || 0)
      .replace('{{ts}}', fmtTs(ds.updated));
    document.getElementById('meta-text').textContent = meta;

    setToggleLabel();

    var modeFilters = document.getElementById('mode-filters');
    modeFilters.innerHTML = '';
    [
      ['all', t('filter_all')],
      ['onsite', t('filter_onsite') + ' (' + (ds.onsite_count || 0) + ')'],
      ['online', t('filter_online') + ' (' + (ds.online_count || 0) + ')'],
    ].forEach(function(pair) {{
      var b = document.createElement('button');
      b.className = 'sas-chip' + (state.mode === pair[0] ? ' active' : '');
      b.textContent = pair[1];
      b.addEventListener('click', function() {{ state.mode = pair[0]; render(); }});
      modeFilters.appendChild(b);
    }});

    renderGrid();
  }}

  document.addEventListener('click', function(e) {{
    if (e.target.closest('[data-stop]')) return; // let action buttons pass through
    var card = e.target.closest('.sas-card[data-uuid]');
    if (card) {{
      var sh = shopsByUuid[card.dataset.uuid];
      if (sh) openModal(sh);
    }}
  }});

  var countrySel = document.getElementById('country-select');
  COUNTRIES.forEach(function(c) {{
    var o = document.createElement('option');
    o.value = c.code; o.textContent = c.name;
    countrySel.appendChild(o);
  }});
  countrySel.value = country;

  var langSel = document.getElementById('language-select');
  function rebuildLangSelector() {{
    var labels = {{ en: 'English', sv: 'Svenska', da: 'Dansk', nb: 'Norsk', fi: 'Suomi' }};
    langSel.innerHTML = '';
    countryDef.languages.forEach(function(l) {{
      var o = document.createElement('option');
      o.value = l; o.textContent = labels[l] || l;
      langSel.appendChild(o);
    }});
    langSel.value = lang;
  }}
  rebuildLangSelector();

  function updateUrl() {{
    var url = new URL(window.location);
    url.searchParams.set('c', country);
    url.searchParams.set('l', lang);
    window.history.replaceState({{}}, '', url);
  }}

  countrySel.addEventListener('change', function() {{
    country = countrySel.value;
    countryDef = COUNTRIES.find(function(c) {{ return c.code === country; }});
    if (countryDef.languages.indexOf(lang) === -1) lang = countryDef.local_lang;
    rebuildLangSelector();
    state.query = '';
    document.getElementById('search-box').value = '';
    updateUrl();
    render();
  }});
  langSel.addEventListener('change', function() {{
    lang = langSel.value;
    updateUrl();
    render();
  }});

  document.getElementById('search-box').addEventListener('input', function(e) {{
    state.query = e.target.value.trim().toLowerCase();
    renderGrid();
  }});

  var stickyWrap = document.getElementById('sticky-wrap');
  var ticking = false;
  window.addEventListener('scroll', function() {{
    if (!ticking) {{
      window.requestAnimationFrame(function() {{
        stickyWrap.classList.toggle('is-stuck', window.scrollY > 20);
        ticking = false;
      }});
      ticking = true;
    }}
  }}, {{ passive: true }});

  updateUrl();
  render();
}})();
</script>

<!-- Cloudflare Web Analytics -->
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "{cf_token}"}}'></script>
<!-- End Cloudflare Web Analytics -->

<!-- GoatCounter -->
<script data-goatcounter="https://eurobonus.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<!-- End GoatCounter -->

</body>
</html>
"""


def main():
    datasets = {c["code"]: prepare_dataset(c["code"]) for c in COUNTRIES}
    HTML_FILE.parent.mkdir(parents=True, exist_ok=True)
    HTML_FILE.write_text(render_html(datasets), encoding="utf-8")
    total = sum(len(d["shops"]) for d in datasets.values())
    print(f"Wrote {HTML_FILE} with {len(datasets)} country datasets, {total} shops total")


if __name__ == "__main__":
    main()
