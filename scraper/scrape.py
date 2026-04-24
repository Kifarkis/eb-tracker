#!/usr/bin/env python3
"""
SAS EuroBonus Shopping tracker.

Fetches current offers from loyaltykey.com every few hours and maintains
two state files:

  data/shops.json    - one entry per shop ever seen (active + gone)
  data/history.json  - append-only log of completed campaigns

Renders a static HTML tracker to docs/index.html.
"""
import html
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_URL = (
    "https://onlineshopping.loyaltykey.com/api/v1/shops"
    "?filter[channel]=SAS"
    "&filter[language]=sv"
    "&filter[country]=SE"
    "&filter[amount]=5000"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SHOPS_FILE = REPO_ROOT / "data" / "shops.json"
HISTORY_FILE = REPO_ROOT / "data" / "history.json"
HTML_FILE = REPO_ROOT / "docs" / "index.html"


def fetch_shops():
    req = Request(API_URL, headers={
        "User-Agent": "Mozilla/5.0 (compatible; sas-shopping-tracker/1.0)",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=30) as response:
        payload = json.load(response)
    return payload.get("data", [])


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def today_iso():
    return date.today().isoformat()


def update_state(api_shops, shops_state, history):
    """
    Reconcile the fresh API response with the persisted state.

    Returns (updated_shops_state, updated_history, summary_counts).
    """
    today = today_iso()
    api_uuids = {s["uuid"] for s in api_shops}
    new_shops_count = 0
    new_campaigns_count = 0
    ended_campaigns_count = 0
    gone_shops_count = 0

    # Update or create entries for shops the API returned.
    for s in api_shops:
        uuid = s["uuid"]
        prev = shops_state.get(uuid, {})
        is_new = not prev

        has_campaign_now = s.get("has_campaign") == 1
        had_campaign_before = bool(prev.get("active_campaign"))
        current_points = s.get("points") or 0
        points_campaign = s.get("points_campaign") or 0
        points_channel = s.get("points_channel") or 0

        # All-time high tracking — we compare against current_points (non-campaign
        # baseline) because campaign points can temporarily spike and we want to
        # record the real highest baseline earning rate we've observed.
        effective_max_this_run = max(current_points, points_campaign)
        prev_high = prev.get("all_time_high_points") or 0
        if effective_max_this_run > prev_high:
            all_time_high_points = effective_max_this_run
            all_time_high_date = today
        else:
            all_time_high_points = prev_high
            all_time_high_date = prev.get("all_time_high_date") or today

        # Campaign state transitions.
        active_campaign = prev.get("active_campaign")
        if has_campaign_now:
            ends_date = s.get("campaign_ends_date")
            if not had_campaign_before:
                # Transition: 0 -> 1. New campaign starts.
                active_campaign = {
                    "started": today,
                    "ends_date": ends_date,
                    "points_campaign": points_campaign,
                    "points_channel": points_channel,
                }
                new_campaigns_count += 1
            else:
                # Still running. Keep original start date but refresh the end
                # date and points in case they shifted mid-campaign.
                active_campaign = {
                    **active_campaign,
                    "ends_date": ends_date,
                    "points_campaign": points_campaign,
                    "points_channel": points_channel,
                }
        else:
            if had_campaign_before:
                # Transition: 1 -> 0. Campaign ended — log it to history.
                history.append({
                    "uuid": uuid,
                    "name": s.get("name") or prev.get("name"),
                    "started": active_campaign.get("started"),
                    "ended": today,
                    "points_campaign": active_campaign.get("points_campaign"),
                    "points_channel": active_campaign.get("points_channel"),
                })
                ended_campaigns_count += 1
            active_campaign = None

        shops_state[uuid] = {
            "uuid": uuid,
            "name": s.get("name"),
            "slug": s.get("slug"),
            "logo": s.get("logo"),
            "first_seen": prev.get("first_seen") or today,
            "last_seen": today,
            "status": "active",
            "current_points": current_points,
            "current_points_channel": points_channel,
            "current_points_campaign": points_campaign if has_campaign_now else 0,
            "currency": s.get("currency"),
            "commission_type": s.get("commission_type"),
            "category_id": s.get("categoryId"),
            "description": s.get("description"),
            "all_time_high_points": all_time_high_points,
            "all_time_high_date": all_time_high_date,
            "active_campaign": active_campaign,
            "campaign_ends_human": s.get("campaign_ends") if has_campaign_now else None,
        }

        if is_new:
            new_shops_count += 1

    # Mark shops that have disappeared from the API as gone.
    for uuid, shop in shops_state.items():
        if uuid in api_uuids:
            continue
        if shop.get("status") != "gone":
            shop["status"] = "gone"
            shop["gone_since"] = today
            gone_shops_count += 1
            # If they had an active campaign when they disappeared, close it.
            if shop.get("active_campaign"):
                history.append({
                    "uuid": uuid,
                    "name": shop.get("name"),
                    "started": shop["active_campaign"].get("started"),
                    "ended": today,
                    "points_campaign": shop["active_campaign"].get("points_campaign"),
                    "points_channel": shop["active_campaign"].get("points_channel"),
                    "note": "shop_disappeared",
                })
                shop["active_campaign"] = None

    summary = {
        "new_shops": new_shops_count,
        "new_campaigns": new_campaigns_count,
        "ended_campaigns": ended_campaigns_count,
        "gone_shops": gone_shops_count,
    }
    return shops_state, history, summary


def points_display(shop):
    """
    Return dict with:
      main       - headline number (campaign if active, else baseline)
      bonus      - campaign lift amount, or 0
      unit       - '/ köp' or '/ 100 kr'
      level      - channel (level) points
      show_campaign - bool
    """
    commission_type = shop.get("commission_type")
    unit = "/ 100 kr" if commission_type == "variable" else "/ köp"
    if shop.get("active_campaign"):
        camp = shop["active_campaign"]
        main = camp.get("points_campaign") or 0
        base = shop.get("current_points") or 0
        bonus = max(main - base, 0)
        return {
            "main": main,
            "bonus": bonus,
            "unit": unit,
            "level": camp.get("points_channel") or 0,
            "show_campaign": True,
        }
    return {
        "main": shop.get("current_points") or 0,
        "bonus": 0,
        "unit": unit,
        "level": shop.get("current_points_channel") or 0,
        "show_campaign": False,
    }


def escape(s):
    return html.escape(str(s or ""), quote=True)


def logo_html(shop):
    logo_url = shop.get("logo")
    if logo_url:
        return f'<img src="{escape(logo_url)}" alt="" class="sas-logo-img" loading="lazy">'
    # Fallback to initials from the shop name.
    name = shop.get("name") or "?"
    parts = [p for p in name.split() if p]
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[1][0]).upper()
    else:
        initials = name[:2].upper()
    return f'<div class="sas-logo-fallback">{escape(initials)}</div>'


def card_html(shop, discovered_today):
    disp = points_display(shop)
    name = escape(shop.get("name"))
    uuid = escape(shop.get("uuid"))
    shop_url = f"https://onlineshopping.flysas.com/sv-SE/butiker/about-you/{uuid}"
    campaign_class = " campaign" if disp["show_campaign"] else ""
    new_dot = '<div class="sas-new-dot" title="Ny kampanj"></div>' if discovered_today else ""

    bonus_pill = (
        f'<span class="sas-pill">+{disp["bonus"]}</span>'
        if disp["bonus"] > 0 else ""
    )

    # Level pill is reserved for the future (when we have history to verify
    # that the level points actually rose compared to baseline). For now
    # we only render a plain level value.
    level_html = f'<span class="sas-status-val">{disp["level"]} p</span>'

    ends_text = escape(shop.get("campaign_ends_human") or "")
    days_remaining = ""
    if disp["show_campaign"] and ends_text:
        urgent_class = ""
        lower = ends_text.lower()
        if "1 dag" in lower or "idag" in lower or "timmar" in lower:
            urgent_class = " urgent"
        days_remaining = (
            f'<span class="sas-days{urgent_class}">{ends_text}</span>'
        )

    return (
        f'<a class="sas-card{campaign_class}" href="{shop_url}" target="_blank" rel="noopener">'
        f'  <div class="sas-card-top">'
        f'    <div class="sas-card-identity">{logo_html(shop)}<div class="sas-card-name">{name}</div></div>'
        f'    {new_dot}'
        f'  </div>'
        f'  <div class="sas-points-block">'
        f'    <div class="sas-points-row">'
        f'      <span class="sas-points-main">{disp["main"]}</span>'
        f'      <span class="sas-eb-tag">EB</span>'
        f'      {bonus_pill}'
        f'      <span class="sas-points-unit">{disp["unit"]}</span>'
        f'    </div>'
        f'    <div class="sas-status-row">'
        f'      <span class="sas-status-label">Nivå</span>'
        f'      {level_html}'
        f'    </div>'
        f'  </div>'
        f'  <div class="sas-card-foot">{days_remaining}</div>'
        f'</a>'
    )


def list_row_html(shop):
    disp = points_display(shop)
    name = escape(shop.get("name"))
    uuid = escape(shop.get("uuid"))
    shop_url = f"https://onlineshopping.flysas.com/sv-SE/butiker/about-you/{uuid}"
    return (
        f'<a class="sas-list-row" href="{shop_url}" target="_blank" rel="noopener">'
        f'  <div class="sas-list-logo-wrap">{logo_html(shop)}</div>'
        f'  <div class="sas-list-name">{name}</div>'
        f'  <div class="sas-list-points">{disp["main"]} EB {disp["unit"]}</div>'
        f'  <div class="sas-list-level">{disp["level"]} nivå</div>'
        f'</a>'
    )


def gone_row_html(shop):
    name = escape(shop.get("name"))
    gone_since = escape(shop.get("gone_since") or "")
    last_seen = escape(shop.get("last_seen") or "")
    return (
        f'<div class="sas-list-row sas-list-row-gone">'
        f'  <div class="sas-list-logo-wrap">{logo_html(shop)}</div>'
        f'  <div class="sas-list-name">{name}</div>'
        f'  <div class="sas-list-points">borta sedan {gone_since or last_seen}</div>'
        f'  <div class="sas-list-level"></div>'
        f'</div>'
    )


def render_html(shops_state):
    today = today_iso()
    active_shops = [s for s in shops_state.values() if s.get("status") == "active"]
    gone_shops = [s for s in shops_state.values() if s.get("status") == "gone"]

    campaigns = [s for s in active_shops if s.get("active_campaign")]
    # Sort campaigns: fixed-point shops first (higher absolute numbers), then
    # variable, each group by main points desc.
    campaigns.sort(key=lambda s: (
        0 if s.get("commission_type") == "fixed" else 1,
        -(points_display(s)["main"]),
        (s.get("name") or "").lower(),
    ))

    non_campaign_active = [s for s in active_shops if not s.get("active_campaign")]
    non_campaign_active.sort(key=lambda s: (s.get("name") or "").lower())

    gone_shops.sort(key=lambda s: s.get("gone_since") or "", reverse=True)

    campaign_cards = "".join(
        card_html(s, discovered_today=(s["active_campaign"].get("started") == today))
        for s in campaigns
    )
    all_rows = "".join(list_row_html(s) for s in non_campaign_active)
    gone_rows = "".join(gone_row_html(s) for s in gone_shops)

    updated_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_active = len(active_shops)
    total_campaigns = len(campaigns)
    total_gone = len(gone_shops)

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>EuroBonus Shopping — kampanjer</title>
<style>
:root {{
  --bg: #faf9f7;
  --surface: #ffffff;
  --border: rgba(0, 0, 0, 0.08);
  --border-strong: rgba(0, 0, 0, 0.16);
  --text: #1a1a1a;
  --text-muted: #6b6b6b;
  --text-faint: #9a9a9a;
  --accent: #1f6feb;
  --accent-bg: rgba(31, 111, 235, 0.08);
  --warn: #b85c00;
}}
html[data-theme="dark"] {{
  --bg: #0f0f10;
  --surface: #1a1a1c;
  --border: rgba(255, 255, 255, 0.08);
  --border-strong: rgba(255, 255, 255, 0.18);
  --text: #ededed;
  --text-muted: #a0a0a0;
  --text-faint: #666666;
  --accent: #6ea8ff;
  --accent-bg: rgba(110, 168, 255, 0.14);
  --warn: #f0a66c;
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  margin: 0;
  padding: 32px 24px 64px;
  font-size: 14px;
  line-height: 1.5;
}}
.sas-container {{ max-width: 1200px; margin: 0 auto; }}
.sas-header {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 24px; gap: 24px; flex-wrap: wrap; }}
.sas-title {{ font-size: 24px; font-weight: 500; letter-spacing: -0.02em; margin: 0 0 4px 0; }}
.sas-meta {{ font-size: 13px; color: var(--text-muted); font-family: ui-monospace, "SF Mono", Menlo, monospace; }}
.sas-toggle {{ background: none; border: 0.5px solid var(--border-strong); color: var(--text-muted); padding: 6px 12px; border-radius: 999px; font-size: 12px; cursor: pointer; font-family: inherit; }}
.sas-toggle:hover {{ color: var(--text); }}
.sas-filters {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
.sas-chip {{ font-size: 13px; padding: 6px 14px; border: 0.5px solid var(--border); border-radius: 999px; background: transparent; color: var(--text-muted); cursor: pointer; font-family: inherit; }}
.sas-chip:hover {{ color: var(--text); }}
.sas-chip.active {{ background: var(--surface); color: var(--text); border-color: var(--border-strong); }}
.sas-section-label {{ font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-faint); margin: 32px 0 12px 0; }}
.sas-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }}
.sas-card {{
  background: var(--surface);
  border: 0.5px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  text-decoration: none;
  color: inherit;
  transition: border-color 0.12s, transform 0.12s;
}}
.sas-card:hover {{ border-color: var(--border-strong); transform: translateY(-1px); }}
.sas-card.campaign {{ border-color: var(--accent); }}
.sas-card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
.sas-card-identity {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
.sas-logo-img {{ width: 22px; height: 22px; border-radius: 4px; object-fit: contain; background: var(--bg); }}
.sas-logo-fallback {{ width: 22px; height: 22px; border-radius: 4px; background: var(--bg); color: var(--text-muted); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 500; letter-spacing: -0.02em; }}
.sas-card-name {{ font-size: 14px; font-weight: 500; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.sas-new-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--accent); flex-shrink: 0; margin-top: 8px; }}
.sas-points-block {{ display: flex; flex-direction: column; gap: 6px; }}
.sas-points-row {{ display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }}
.sas-points-main {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 20px; font-weight: 500; letter-spacing: -0.02em; line-height: 1; }}
.sas-eb-tag {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 10px; font-weight: 500; color: var(--text-faint); letter-spacing: 0.04em; }}
.sas-pill {{ display: inline-block; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px; padding: 2px 7px; background: var(--accent-bg); color: var(--accent); border-radius: 999px; }}
.sas-points-unit {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px; color: var(--text-faint); }}
.sas-status-row {{ display: flex; align-items: baseline; gap: 6px; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12px; }}
.sas-status-label {{ color: var(--text-faint); font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; }}
.sas-status-val {{ color: var(--text-muted); }}
.sas-card-foot {{ display: flex; font-size: 12px; color: var(--text-muted); font-family: ui-monospace, "SF Mono", Menlo, monospace; padding-top: 8px; border-top: 0.5px solid var(--border); min-height: 28px; align-items: center; }}
.sas-days.urgent {{ color: var(--warn); }}
.sas-list {{ display: flex; flex-direction: column; }}
.sas-list-row {{ display: grid; grid-template-columns: 28px 1fr auto auto; gap: 12px; align-items: center; padding: 10px 0; border-bottom: 0.5px solid var(--border); text-decoration: none; color: inherit; }}
.sas-list-row:hover .sas-list-name {{ color: var(--accent); }}
.sas-list-row-gone {{ opacity: 0.55; }}
.sas-list-logo-wrap {{ width: 22px; height: 22px; }}
.sas-list-name {{ font-size: 14px; }}
.sas-list-points {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 13px; color: var(--text-muted); min-width: 120px; text-align: right; }}
.sas-list-level {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px; color: var(--text-faint); min-width: 70px; text-align: right; }}
.sas-hidden {{ display: none !important; }}
@media (max-width: 640px) {{
  body {{ padding: 20px 14px 48px; }}
  .sas-list-level {{ display: none; }}
  .sas-list-points {{ min-width: 100px; }}
}}
</style>
</head>
<body>
<div class="sas-container">
  <div class="sas-header">
    <div>
      <h1 class="sas-title">EuroBonus Shopping</h1>
      <div class="sas-meta">{total_campaigns} aktiva kampanjer · {total_active} butiker · uppdaterad {updated_ts}</div>
    </div>
    <button class="sas-toggle" id="theme-toggle" aria-label="Växla tema">Tema</button>
  </div>

  <div class="sas-filters" role="tablist">
    <button class="sas-chip active" data-view="all">Alla</button>
    <button class="sas-chip" data-view="campaigns">Kampanjer</button>
    <button class="sas-chip" data-view="ending">Slutar snart</button>
    <button class="sas-chip" data-view="gone">Borta ({total_gone})</button>
  </div>

  <section data-section="campaigns">
    <div class="sas-section-label">Aktiva kampanjer</div>
    <div class="sas-grid">{campaign_cards if campaign_cards else '<div style="color: var(--text-faint); font-size: 13px; padding: 12px 0;">Inga aktiva kampanjer just nu.</div>'}</div>
  </section>

  <section data-section="all-shops">
    <div class="sas-section-label">Alla butiker</div>
    <div class="sas-list">{all_rows}</div>
  </section>

  <section data-section="gone" class="sas-hidden">
    <div class="sas-section-label">Butiker som försvunnit</div>
    <div class="sas-list">{gone_rows if gone_rows else '<div style="color: var(--text-faint); font-size: 13px; padding: 12px 0;">Inga försvunna butiker ännu.</div>'}</div>
  </section>
</div>

<script>
(function() {{
  var root = document.documentElement;
  var toggle = document.getElementById('theme-toggle');
  var stored = null;
  try {{ stored = localStorage.getItem('sas-theme'); }} catch (e) {{}}
  function apply(theme) {{
    if (theme === 'dark' || theme === 'light') {{
      root.setAttribute('data-theme', theme);
    }} else {{
      root.removeAttribute('data-theme');
    }}
  }}
  apply(stored);
  toggle.addEventListener('click', function() {{
    var current = root.getAttribute('data-theme');
    var next;
    if (!current) {{
      next = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark';
    }} else {{
      next = current === 'dark' ? 'light' : 'dark';
    }}
    apply(next);
    try {{ localStorage.setItem('sas-theme', next); }} catch (e) {{}}
  }});

  var chips = document.querySelectorAll('.sas-chip');
  var sectionCampaigns = document.querySelector('[data-section="campaigns"]');
  var sectionAll = document.querySelector('[data-section="all-shops"]');
  var sectionGone = document.querySelector('[data-section="gone"]');

  function setView(view) {{
    chips.forEach(function(c) {{ c.classList.toggle('active', c.dataset.view === view); }});
    sectionCampaigns.classList.remove('sas-hidden');
    sectionAll.classList.remove('sas-hidden');
    sectionGone.classList.add('sas-hidden');
    if (view === 'campaigns') {{
      sectionAll.classList.add('sas-hidden');
    }} else if (view === 'ending') {{
      sectionAll.classList.add('sas-hidden');
      sectionCampaigns.querySelectorAll('.sas-card').forEach(function(card) {{
        var urgent = card.querySelector('.sas-days.urgent');
        card.style.display = urgent ? '' : 'none';
      }});
      return;
    }} else if (view === 'gone') {{
      sectionCampaigns.classList.add('sas-hidden');
      sectionAll.classList.add('sas-hidden');
      sectionGone.classList.remove('sas-hidden');
    }}
    sectionCampaigns.querySelectorAll('.sas-card').forEach(function(card) {{ card.style.display = ''; }});
  }}

  chips.forEach(function(c) {{
    c.addEventListener('click', function() {{ setView(c.dataset.view); }});
  }});
}})();
</script>
</body>
</html>
"""


def main():
    print(f"Fetching {API_URL}")
    try:
        api_shops = fetch_shops()
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Got {len(api_shops)} shops from API")
    if len(api_shops) < 50:
        print(
            f"WARNING: only {len(api_shops)} shops returned — pagination may have kicked in",
            file=sys.stderr,
        )

    shops_state = load_json(SHOPS_FILE, {})
    history = load_json(HISTORY_FILE, [])

    shops_state, history, summary = update_state(api_shops, shops_state, history)

    print(
        f"Transitions this run: "
        f"{summary['new_shops']} new shops, "
        f"{summary['new_campaigns']} new campaigns, "
        f"{summary['ended_campaigns']} ended campaigns, "
        f"{summary['gone_shops']} newly gone shops"
    )

    save_json(SHOPS_FILE, shops_state)
    save_json(HISTORY_FILE, history)
    HTML_FILE.parent.mkdir(parents=True, exist_ok=True)
    HTML_FILE.write_text(render_html(shops_state), encoding="utf-8")
    print(f"Wrote {SHOPS_FILE}, {HISTORY_FILE}, and {HTML_FILE}")


if __name__ == "__main__":
    main()
