#!/usr/bin/env python3
"""Render the daily pulse as a single self-contained HTML dashboard.

Style: cbti.club — luxury editorial on black. Instrument Serif + Barlow + JetBrains Mono.
Liquid glass cards, film grain, ambient radial glow, pill CTAs.

Usage:
  render_dashboard.py <pulse_data.json> [output.html]

If output is omitted, writes to ~/Documents/Last30Days/x-pulse-YYYY-MM-DD.html
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

QUEUE_PENDING = ROOT / "queue" / "pending"


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


def _parse_ts(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(str(ts), "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


def _hours_since(ts) -> float:
    dt = _parse_ts(ts)
    if not dt:
        return 1e9
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def _engagement_score(t: dict) -> int:
    if t.get("impression_count"):
        return int(t["impression_count"])
    return (
        int(t.get("like_count", 0) or 0) * 10
        + int(t.get("retweet_count", 0) or 0) * 30
        + int(t.get("reply_count", 0) or 0) * 5
    )


def _eng_bits(t: dict) -> str:
    parts = []
    if t.get("like_count"):
        parts.append(f'<span class="m heart">{int(t["like_count"])}❤</span>')
    if t.get("retweet_count"):
        parts.append(f'<span class="m">{int(t["retweet_count"])}🔁</span>')
    if t.get("reply_count"):
        parts.append(f'<span class="m">{int(t["reply_count"])}💬</span>')
    if t.get("impression_count"):
        parts.append(f'<span class="m imp">{int(t["impression_count"]):,}👁</span>')
    return " ".join(parts) or '<span class="m muted">0 engagement</span>'


def _short(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


# ── load pending queue ────────────────────────────────────────────────────────
def load_pending() -> list[dict]:
    drafts = []
    if not QUEUE_PENDING.exists():
        return drafts
    for p in sorted(QUEUE_PENDING.glob("*.md")):
        raw = p.read_text()
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        body = m.group(2).strip()
        tweets = [c.strip() for c in re.split(r"\n\s*\n", body) if c.strip()] or [body]
        drafts.append({
            "name": p.name,
            "fm": fm,
            "tweets": tweets,
            "body": body,
        })
    return drafts


# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = r"""
/* x-control dashboard — cbti.club design system
   black surface · liquid glass · serif display · film grain */
:root {
  --bg:#050506; --bg2:#0A0A0D;
  --fg:#FFFFFF;
  --fg-70:rgba(255,255,255,.70); --fg-60:rgba(255,255,255,.60);
  --fg-50:rgba(255,255,255,.50); --fg-40:rgba(255,255,255,.40);
  --fg-20:rgba(255,255,255,.20); --fg-10:rgba(255,255,255,.10);
  --fg-06:rgba(255,255,255,.06);
  --green:#00E676;
  --purple:#B24BF3;
  --yellow:#FFB800;
  --red:#FF2E4C;
  --r-pill:9999px; --r-card:20px; --r-card-sm:12px;
  --s-1:4px; --s-2:8px; --s-3:12px; --s-4:16px;
  --s-5:24px; --s-6:32px; --s-7:48px; --s-8:64px;
  --max-w:760px;
  --font-display:'Instrument Serif','Noto Serif SC',ui-serif,Georgia,serif;
  --font-body:'Barlow','Noto Sans SC',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --font-mono:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{
  background:var(--bg); color:var(--fg);
  font-family:var(--font-body); font-weight:400; line-height:1.5;
  letter-spacing:-.005em;
  -webkit-font-smoothing:antialiased;
}
body{min-height:100vh; position:relative; overflow-x:hidden; padding-bottom:var(--s-8)}

/* ambient radial glow */
body::before{
  content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(ellipse 70% 50% at 50% -20%, rgba(255,255,255,.04), transparent 60%),
    radial-gradient(ellipse 60% 40% at 50% 120%, rgba(255,255,255,.02), transparent 60%);
}
/* film grain */
body::after{
  content:''; position:fixed; inset:0; pointer-events:none; z-index:1;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.06 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
  opacity:.5; mix-blend-mode:overlay; transform:translateZ(0);
}

main{
  position:relative; z-index:2;
  max-width:var(--max-w); margin:0 auto;
  padding:var(--s-7) var(--s-5);
}

/* ── header ────────────────────────────────────────────── */
header{margin-bottom:var(--s-7)}
header h1{
  font-family:var(--font-display); font-weight:400;
  font-size:clamp(48px,8vw,80px); line-height:.95; letter-spacing:-.02em;
}
header h1 em{font-style:italic; color:var(--fg-60)}
.date{
  font-family:var(--font-mono); color:var(--fg-50);
  font-size:13px; margin-top:var(--s-2); letter-spacing:.02em;
}

/* status pills row */
.status-row{
  display:flex; flex-wrap:wrap; gap:var(--s-2);
  margin-top:var(--s-4);
}
.pill{
  display:inline-flex; align-items:center; gap:var(--s-2);
  padding:6px 12px; border-radius:var(--r-pill);
  background:rgba(255,255,255,.04);
  border:1px solid var(--fg-10);
  font-family:var(--font-mono); font-size:12px;
  color:var(--fg-70);
}
.pill .dot{width:6px; height:6px; border-radius:50%; display:inline-block}
.dot.ok{background:var(--green); box-shadow:0 0 8px rgba(0,230,118,.5)}
.dot.fail{background:var(--red); box-shadow:0 0 8px rgba(255,46,76,.5)}
.dot.empty{background:var(--fg-40)}
.pill .count{color:var(--fg)}

/* ── cards ─────────────────────────────────────────────── */
section{margin-bottom:var(--s-5)}
.glass{
  position:relative; overflow:hidden;
  border-radius:var(--r-card);
  padding:var(--s-5) var(--s-5);
  background:rgba(255,255,255,.018);
  background-blend-mode:luminosity;
  backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.08), 0 1px 2px rgba(0,0,0,.4);
}
.glass::before{
  content:''; position:absolute; inset:0; border-radius:inherit;
  padding:1px;
  background:linear-gradient(180deg,
    rgba(255,255,255,.35) 0%,
    rgba(255,255,255,.12) 20%,
    rgba(255,255,255,0) 40%,
    rgba(255,255,255,0) 60%,
    rgba(255,255,255,.10) 80%,
    rgba(255,255,255,.30) 100%);
  -webkit-mask:linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite:xor; mask-composite:exclude;
  pointer-events:none;
}
.glass-strong{
  background:rgba(255,255,255,.02);
  backdrop-filter:blur(40px); -webkit-backdrop-filter:blur(40px);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.18), 0 4px 24px rgba(0,0,0,.35);
}

h2{
  font-family:var(--font-display); font-weight:400;
  font-size:28px; line-height:1.1; letter-spacing:-.01em;
  margin-bottom:var(--s-4);
}
h2 .accent{color:var(--green)}
h3{
  font-family:var(--font-body); font-weight:500;
  font-size:13px; text-transform:uppercase; letter-spacing:.12em;
  color:var(--fg-50);
  margin:var(--s-5) 0 var(--s-3);
}

/* TL;DR */
.decision-list{list-style:none; display:flex; flex-direction:column; gap:var(--s-4)}
.decision-list li{
  position:relative; padding-left:var(--s-5);
  font-size:16px; line-height:1.55; color:var(--fg-70);
}
.decision-list li b{color:var(--fg); font-weight:600}
.decision-list li::before{
  content:'•'; color:var(--fg-40);
  font-family:var(--font-mono);
  position:absolute; left:0; top:0;
}
.decision-list code{
  font-family:var(--font-mono); font-size:12px;
  color:var(--fg-60); background:var(--fg-06);
  padding:1px 6px; border-radius:4px;
}
.decision-list a{color:var(--fg); text-decoration:underline; text-decoration-color:var(--fg-20); text-underline-offset:3px}
.decision-list a:hover{text-decoration-color:var(--fg-70)}

/* mentions */
.mentions{list-style:none; display:flex; flex-direction:column; gap:var(--s-3)}
.mentions li{
  display:flex; gap:var(--s-3); align-items:flex-start;
  padding:var(--s-3) 0; border-top:1px solid var(--fg-10);
}
.mentions li:first-child{border-top:none; padding-top:0}
.mentions .urg{
  flex-shrink:0; width:8px; height:8px; border-radius:50%;
  margin-top:8px;
}
.mentions .urg.red{background:var(--red); box-shadow:0 0 10px rgba(255,46,76,.4)}
.mentions .urg.yellow{background:var(--yellow); box-shadow:0 0 8px rgba(255,184,0,.4)}
.mentions .urg.green{background:var(--green); box-shadow:0 0 8px rgba(0,230,118,.4)}
.mentions .body{flex:1; min-width:0}
.mentions .who{font-weight:500; color:var(--fg)}
.mentions .meta{color:var(--fg-50); font-family:var(--font-mono); font-size:12px}
.mentions .text{
  color:var(--fg-70); margin-top:2px; font-size:15px;
  overflow:hidden; text-overflow:ellipsis;
}
.mentions a{color:inherit; text-decoration:none}
.mentions a:hover .text{color:var(--fg)}
.more{color:var(--fg-50); font-size:13px; font-style:italic; padding-top:var(--s-2)}

/* own tweets */
.pattern{
  font-family:var(--font-mono); font-size:12px;
  color:var(--fg-60);
  padding:var(--s-3) var(--s-4); margin-bottom:var(--s-4);
  background:var(--fg-06); border-radius:var(--r-card-sm);
  border-left:2px solid var(--fg-20);
}
.tweet{
  display:grid; grid-template-columns:180px 1fr; gap:var(--s-3);
  padding:var(--s-3) 0;
  border-top:1px solid var(--fg-10);
  align-items:start;
}
.tweet:first-of-type{border-top:none; padding-top:0}
.tweet .eng{
  display:flex; flex-wrap:wrap; gap:4px 10px;
  align-content:flex-start; min-width:0;
}
.tweet .eng .m{font-family:var(--font-mono); font-size:12px; color:var(--fg-70); white-space:nowrap}
.tweet .eng .m.heart{color:var(--red)}
.tweet .eng .m.imp{color:var(--fg-50)}
.tweet .eng .m.muted{color:var(--fg-40)}
.tweet .text{
  min-width:0; color:var(--fg-70); font-size:14px; line-height:1.5;
  overflow-wrap:anywhere;
}
.tweet .text a{color:inherit; text-decoration:none}
.tweet .text a:hover{color:var(--fg); text-decoration:underline; text-decoration-color:var(--fg-40)}

@media (max-width:560px){
  .tweet{grid-template-columns:1fr; gap:var(--s-2)}
}

/* warnings */
.warn{
  padding:var(--s-3) var(--s-4); border-radius:var(--r-card-sm);
  font-size:13px; line-height:1.5;
  margin:var(--s-4) 0;
}
.warn.yellow{
  background:rgba(255,184,0,.05); border:1px solid rgba(255,184,0,.3);
  color:rgba(255,184,0,.95);
}
.warn.red{
  background:rgba(255,46,76,.06); border:1px solid rgba(255,46,76,.3);
  color:rgba(255,46,76,.95);
}
.warn b{color:inherit}
.warn code{font-family:var(--font-mono); font-size:11px; opacity:.75}

/* KOL table */
table.kol{
  width:100%; border-collapse:collapse;
  font-family:var(--font-mono); font-size:13px;
}
table.kol th{
  text-align:left; padding:var(--s-2) var(--s-3);
  color:var(--fg-50); font-weight:500;
  text-transform:uppercase; letter-spacing:.08em; font-size:11px;
  border-bottom:1px solid var(--fg-10);
}
table.kol td{
  padding:var(--s-2) var(--s-3); color:var(--fg-70);
  border-bottom:1px solid var(--fg-06);
}
table.kol tr:last-child td{border-bottom:none}
table.kol .flag{color:var(--yellow)}
.quiet{font-size:12px; color:var(--fg-50); margin-top:var(--s-3); font-style:italic}
.kol-active{display:flex; flex-direction:column; gap:var(--s-1); font-family:var(--font-mono); font-size:13px}
.kol-active .row{display:flex; justify-content:space-between; align-items:baseline; gap:var(--s-3)}
.kol-active .row .h{color:var(--fg)}
.kol-active .row .v{color:var(--fg-70)}

/* drafts */
.draft{
  margin-bottom:var(--s-3);
  padding:var(--s-4);
  background:var(--fg-06);
  border-radius:var(--r-card-sm);
  border-left:2px solid var(--purple);
}
.draft .meta{font-family:var(--font-mono); font-size:11px; color:var(--fg-50); margin-bottom:var(--s-2)}
.draft .tweet-block{
  font-family:var(--font-body); font-size:14px; color:var(--fg);
  white-space:pre-wrap; word-break:break-word;
  padding:var(--s-2) 0;
}
.draft .tweet-block + .tweet-block{border-top:1px dashed var(--fg-10); margin-top:var(--s-2); padding-top:var(--s-3)}
.draft .risk{color:var(--red); font-family:var(--font-mono); font-size:11px; margin-top:var(--s-2)}

/* CTA pill — used for approve-in-CLI hint and external links */
.cta-row{
  display:flex; flex-wrap:wrap; gap:var(--s-2);
  margin-top:var(--s-3); padding-top:var(--s-3);
  border-top:1px solid var(--fg-10);
}
.cta{
  display:inline-flex; align-items:center; gap:var(--s-2);
  padding:8px 16px; border-radius:var(--r-pill);
  background:rgba(255,255,255,.04);
  border:1px solid var(--fg-20);
  color:var(--fg); text-decoration:none;
  font-family:var(--font-mono); font-size:12px;
  transition:all .18s cubic-bezier(.16,1,.3,1);
}
.cta:hover{background:rgba(255,255,255,.08); border-color:var(--fg-40)}
.cta.primary{background:var(--fg); color:var(--bg); border-color:var(--fg)}
.cta.primary:hover{background:var(--fg-70)}
.cta code{font-family:inherit; opacity:.7}

/* footer */
footer{
  margin-top:var(--s-7); padding-top:var(--s-5);
  border-top:1px solid var(--fg-10);
  font-family:var(--font-mono); font-size:11px; color:var(--fg-50);
}
footer pre{white-space:pre-wrap; color:var(--fg-60); font-family:inherit}
footer .gen{margin-top:var(--s-3); color:var(--fg-40)}
"""


# ── HTML helpers ──────────────────────────────────────────────────────────────
def _status_pills(data: dict) -> str:
    mentions = (data.get("own_mentions") or {}).get("data") or []
    own_count = len(data.get("own_tweets") or [])
    mention_count = len(mentions)
    kol_count = len(data.get("kol_rows") or [])
    viral_count = len(data.get("viral_posts") or [])
    failure_text = " ".join(data.get("failures") or []).lower()
    own_fail = any(k in failure_text for k in ("own block", "oauth", "official."))
    mentions_fail = any(k in failure_text for k in ("me_mentions", "mentions"))
    kol_fail = any(k in failure_text for k in ("kol block", "last30days", "bird"))
    def cell(label, count, fail):
        if not count and fail:
            cls = "fail"
        elif count == 0:
            cls = "empty"
        else:
            cls = "ok"
        return f'<span class="pill"><span class="dot {cls}"></span>{label} <span class="count">{count}</span></span>'
    return (
        cell("own", own_count, own_fail)
        + cell("mentions", mention_count, mentions_fail)
        + cell("KOLs", kol_count, kol_fail)
        + cell("viral", viral_count, False if viral_count else False)
    )


def _decision_block(data: dict) -> str:
    own = data.get("own_handle") or "you"
    own_tweets = data.get("own_tweets") or []
    own_count = len(own_tweets)
    mentions_block = data.get("own_mentions") or {}
    mentions = mentions_block.get("data") or []
    includes = mentions_block.get("includes") or {}
    users = {u["id"]: u for u in includes.get("users", [])} if includes else {}
    items: list[str] = []

    burst = own_count >= 4
    if burst:
        items.append(
            f"<b>Hold standalone posts.</b> {own_count} in 24h — "
            "<code>AuthorDiversityDecay</code> "
            "(<code>home-mixer/scorers/ranking_scorer.rs:195-196</code>) biting. "
            "Reply or thread instead (a thread is one author event)."
        )
    elif own_count == 0:
        items.append(
            "<b>Open window.</b> No posts today — fresh "
            "<code>AuthorDiversityDecay</code> slot."
        )
    else:
        remaining = max(0, 3 - own_count)
        items.append(
            f"<b>Post budget:</b> {remaining} standalone posts left before "
            "<code>AuthorDiversityDecay</code> penalty (4+ in 24h)."
        )

    trapped = [
        t for t in own_tweets
        if (t.get("reply_count", 0) or 0) >= 3 and (t.get("like_count", 0) or 0) <= 1
    ]
    if trapped:
        worst = max(trapped, key=lambda t: t.get("reply_count", 0))
        url = f"https://x.com/{own}/status/{worst.get('id')}"
        items.append(
            f"<b>{len(trapped)} OON-trapped tweet{'s' if len(trapped) > 1 else ''}</b> "
            f"— worst: <a href='{_esc(url)}' target='_blank' rel='noopener'>"
            f"{worst.get('reply_count', 0)} replies / {worst.get('like_count', 0)} likes</a>. "
            "<code>OON_WEIGHT_FACTOR</code> suppression. Delete or quote-reframe."
        )

    if mentions:
        scored = []
        for m in mentions:
            author = users.get(m.get("author_id"), {})
            followers = ((author.get("public_metrics") or {}).get("followers_count")) or 0
            age = _hours_since(m.get("created_at"))
            recency = math.exp(-age / 24.0)
            score = math.log10(max(followers, 1) + 1) * recency
            scored.append((score, followers, age, m, author))
        scored.sort(key=lambda x: x[0], reverse=True)
        _, top_followers, _, top_m, top_author = scored[0]
        uname = top_author.get("username", "unknown")
        snippet = _short(top_m.get("text", ""), 80)
        items.append(
            f"<b>Top reply target:</b> @{_esc(uname)} ({top_followers:,} followers) — "
            f"\"{_esc(snippet)}\". ({len(mentions)} total mentions unreplied.)"
        )

    if data.get("viral_posts"):
        v = data["viral_posts"][0]
        t = v["tweet"]
        items.append(
            f"<b>Viral KOL to quote:</b> @{_esc(v['handle'])} "
            f"({t.get('like_count', 0)}❤ {t.get('reply_count', 0)}💬) — "
            f"\"{_esc(_short(t.get('text', ''), 100))}\". Manual quote on x.com."
        )

    # Tomorrow's gap
    if own_tweets:
        cn = sum(1 for t in own_tweets if re.search(r"[一-鿿]", t.get("text", "")))
        en = len(own_tweets) - cn
        replies = sum(1 for t in own_tweets if t.get("text", "").lstrip().startswith("@"))
        originals = len(own_tweets) - replies
        with_link = sum(1 for t in own_tweets if re.search(r"https?://|t\.co/", t.get("text", "")))
        avg_likes = sum((t.get("like_count", 0) or 0) for t in own_tweets) / max(len(own_tweets), 1)
        gaps = []
        if en == 0 and cn >= 3:
            gaps.append("0 EN originals today — propose ≥1 EN long-form")
        if originals == 0 and replies >= 3:
            gaps.append("all replies today — propose ≥1 original thread")
        if with_link == 0 and len(own_tweets) >= 3:
            gaps.append("0 link-bearing posts")
        if avg_likes < 1 and len(own_tweets) >= 3:
            gaps.append("avg &lt;1❤ across posts — angle missing in-network resonance")
        if gaps:
            items.append("<b>Tomorrow's gap:</b> " + "; ".join(gaps) + ".")

    return "<ul class='decision-list'>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


def _mentions_block(data: dict) -> str:
    mentions_block = data.get("own_mentions") or {}
    mentions = mentions_block.get("data") or []
    if not mentions:
        return ""
    includes = mentions_block.get("includes") or {}
    users = {u["id"]: u for u in includes.get("users", [])} if includes else {}
    scored = []
    for m in mentions:
        author = users.get(m.get("author_id"), {})
        followers = ((author.get("public_metrics") or {}).get("followers_count")) or 0
        age = _hours_since(m.get("created_at"))
        recency = math.exp(-age / 24.0)
        score = math.log10(max(followers, 1) + 1) * recency
        scored.append((score, followers, age, m, author))
    scored.sort(key=lambda x: x[0], reverse=True)
    shown = 3 if len(scored) > 4 else len(scored)
    rows = []
    for _, followers, age_h, m, author in scored[:shown]:
        uname = author.get("username", "unknown")
        tid = m.get("id")
        urg = "red" if age_h < 6 else ("yellow" if age_h < 24 else "green")
        age_str = f"{age_h:.0f}h" if age_h < 48 else f"{age_h/24:.0f}d"
        rows.append(
            f'<li><span class="urg {urg}"></span><div class="body">'
            f'<a href="https://x.com/{_esc(uname)}/status/{_esc(tid)}" target="_blank" rel="noopener">'
            f'<div><span class="who">@{_esc(uname)}</span> '
            f'<span class="meta">{followers:,} · {age_str} ago</span></div>'
            f'<div class="text">{_esc(_short(m.get("text", ""), 200))}</div>'
            f'</a></div></li>'
        )
    extra = ""
    if len(scored) > shown:
        oldest_h = scored[-1][2]
        oldest_str = f"{oldest_h:.0f}h" if oldest_h < 48 else f"{oldest_h/24:.0f}d"
        extra = f'<div class="more">+ {len(scored) - shown} more, oldest {oldest_str} ago</div>'
    return (
        '<section class="glass"><h2>Unanswered <em>mentions</em></h2>'
        '<ol class="mentions">' + "".join(rows) + '</ol>' + extra + '</section>'
    )


def _own_block(data: dict) -> str:
    own_tweets = data.get("own_tweets") or []
    if not own_tweets:
        return ('<section class="glass"><h2>Your account</h2>'
                '<p style="color:var(--fg-50)">No tweets in the last 24h, or own block failed.</p></section>')
    own = data.get("own_handle") or "you"
    # Pattern rollup
    cn = sum(1 for t in own_tweets if re.search(r"[一-鿿]", t.get("text", "")))
    en = len(own_tweets) - cn
    replies = sum(1 for t in own_tweets if t.get("text", "").lstrip().startswith("@"))
    originals = len(own_tweets) - replies
    with_link = sum(1 for t in own_tweets if re.search(r"https?://|t\.co/", t.get("text", "")))
    avg_likes = sum((t.get("like_count", 0) or 0) for t in own_tweets) / max(len(own_tweets), 1)
    pattern = (
        f"Pattern: {cn} CN + {en} EN, {replies} replies + {originals} originals, "
        f"{with_link} with links · Avg {avg_likes:.1f}❤/post"
    )
    ranked = sorted(own_tweets, key=_engagement_score, reverse=True)

    def tweet_row(t):
        return (
            f'<div class="tweet"><div class="eng">{_eng_bits(t)}</div>'
            f'<div class="text"><a href="https://x.com/{_esc(own)}/status/{_esc(t.get("id"))}" '
            f'target="_blank" rel="noopener">{_esc(_short(t.get("text", ""), 200))}</a></div></div>'
        )
    top_html = "".join(tweet_row(t) for t in ranked[:3])
    bottom_html = ""
    if len(ranked) > 3:
        bottom_html = (
            '<h3>Topics to NOT repeat tomorrow</h3>'
            + "".join(tweet_row(t) for t in ranked[-min(3, len(ranked) - 3):])
        )

    trapped = [
        t for t in own_tweets
        if (t.get("reply_count", 0) or 0) >= 3 and (t.get("like_count", 0) or 0) <= 1
    ]
    trapped_html = ""
    if trapped:
        trapped_html = (
            '<div class="warn red"><b>⚠ OON-trapped</b> (replies ≥ 3, likes ≤ 1) — '
            '<code>OON_WEIGHT_FACTOR (oon_scorer.rs:21)</code> suppression. Delete or quote-reframe.</div>'
            + "".join(tweet_row(t) for t in trapped)
        )
    burst_html = ""
    if len(own_tweets) >= 4:
        burst_html = (
            f'<div class="warn yellow"><b>⚠ Burst window: {len(own_tweets)} posts in last 24h.</b> '
            '<code>AuthorDiversityDecay (ranking_scorer.rs:195-196)</code> penalizes the same '
            'author shown repeatedly. Threads = one author event.</div>'
        )

    return (
        '<section class="glass"><h2>Your <em>account</em></h2>'
        f'<div class="pattern">{_esc(pattern)}</div>'
        '<h3>Top performers (last 24h)</h3>'
        + top_html
        + trapped_html
        + burst_html
        + bottom_html
        + '</section>'
    )


def _kol_block(data: dict) -> str:
    rows = data.get("kol_rows") or []
    if not rows:
        return ""
    sortable = [r for r in rows if r.get("velocity_ratio") is not None]
    baseline = [r for r in rows if r.get("velocity_ratio") is None]
    active = [r for r in baseline if r.get("tweet_count_24h", 0) > 0]
    quiet = [r for r in baseline if r.get("tweet_count_24h", 0) == 0]

    html_parts: list[str] = []
    html_parts.append('<section class="glass"><h2>KOL <em>posting velocity</em></h2>')
    if sortable:
        sortable.sort(key=lambda r: r.get("velocity_ratio") or 0, reverse=True)
        html_parts.append('<table class="kol"><thead><tr>'
                          '<th>handle</th><th>cat</th><th>24h</th><th>prior</th>'
                          '<th>Δ</th><th>×</th><th></th></tr></thead><tbody>')
        for r in sortable:
            sign = "+" if (r.get("velocity_delta") or 0) >= 0 else ""
            flag = '<span class="flag">⚡</span>' if r.get("flagged") else ""
            html_parts.append(
                f'<tr><td>@{_esc(r["handle"])}</td><td>{_esc(r.get("category","?"))}</td>'
                f'<td>{r["tweet_count_24h"]}</td><td>{r["prev_count"]}</td>'
                f'<td>{sign}{r["velocity_delta"]}</td><td>{r["velocity_ratio"]:.2f}×</td>'
                f'<td>{flag}</td></tr>'
            )
        html_parts.append('</tbody></table>')
    if active:
        html_parts.append('<h3>Baseline (active, no prior snapshot)</h3>')
        active.sort(key=lambda r: r["tweet_count_24h"], reverse=True)
        html_parts.append('<div class="kol-active">')
        for r in active:
            html_parts.append(
                f'<div class="row"><span class="h">@{_esc(r["handle"])} '
                f'<span style="color:var(--fg-50);font-size:11px">{_esc(r.get("category","?"))}</span></span>'
                f'<span class="v">{r["tweet_count_24h"]} tweets/24h</span></div>'
            )
        html_parts.append('</div>')
    if quiet:
        from collections import Counter
        cats = Counter(r.get("category", "?") for r in quiet)
        if len(quiet) >= 5 and len(cats) >= 2:
            by_cat = ", ".join(f"{n} {c}" for c, n in cats.most_common())
            html_parts.append(f'<div class="quiet">Quiet last 24h ({len(quiet)}): {by_cat}</div>')
        else:
            handles = ", ".join(f"@{r['handle']}" for r in quiet)
            html_parts.append(f'<div class="quiet">Quiet last 24h ({len(quiet)}): {handles}</div>')
    html_parts.append('</section>')
    return "".join(html_parts)


def _viral_block(data: dict) -> str:
    viral = data.get("viral_posts") or []
    if not viral:
        return ""
    viral.sort(
        key=lambda v: (v["tweet"].get("like_count", 0) or 0) + (v["tweet"].get("reply_count", 0) or 0),
        reverse=True,
    )
    rows = []
    for v in viral:
        t = v["tweet"]
        rows.append(
            f'<div class="tweet"><div class="eng">{_eng_bits(t)}</div>'
            f'<div class="text"><a href="{_esc(v["url"])}" target="_blank" rel="noopener">'
            f'<b>@{_esc(v["handle"])}</b> — {_esc(_short(t.get("text",""), 220))}</a></div></div>'
        )
    return (
        '<section class="glass"><h2>Viral <em>KOL posts</em></h2>'
        '<h3>≥500 likes OR ≥100 replies, last 24h</h3>'
        + "".join(rows) + '</section>'
    )


def _drafts_block() -> str:
    drafts = load_pending()
    if not drafts:
        return (
            '<section class="glass"><h2>Pending <em>drafts</em></h2>'
            '<p style="color:var(--fg-50)">Queue is empty. /x-brief will drop drafts here when it runs.</p>'
            '</section>'
        )
    items = []
    for d in drafts:
        fm = d["fm"]
        cc = fm.get("character_count", 0)
        url_count = fm.get("url_count", 0)
        kind = fm.get("type", "post")
        target = fm.get("target_time") or "—"
        is_thread = len(d["tweets"]) > 1
        meta = (
            f'{d["name"]} · type={kind} · target={_esc(target)} · '
            f'{cc} chars · {url_count} urls'
            + (f' · thread ({len(d["tweets"])} tweets)' if is_thread else '')
        )
        blocks = "".join(f'<div class="tweet-block">{_esc(t)}</div>' for t in d["tweets"])
        items.append(
            f'<div class="draft"><div class="meta">{_esc(meta)}</div>{blocks}</div>'
        )
    cmd = "~/.claude/skills/x-control/.venv/bin/python ~/.claude/skills/x-control/scripts/approve.py"
    return (
        '<section class="glass"><h2>Pending <em>drafts</em></h2>'
        f'<p style="color:var(--fg-60);margin-bottom:var(--s-4)">{len(drafts)} draft{"s" if len(drafts) > 1 else ""} awaiting approval.</p>'
        + "".join(items)
        + f'<div class="cta-row">'
        f'<span class="cta primary">Approve in CLI</span>'
        f'<span class="cta"><code>{_esc(cmd)}</code></span>'
        f'</div>'
        '</section>'
    )


def _warnings_block(data: dict) -> str:
    failures = data.get("failures") or []
    if not failures:
        return ""
    block_level = [
        f for f in failures
        if any(t in f for t in ("OAuth", "official", "last30days:", "cost cap", "own block", "KOL block"))
    ]
    if not block_level:
        return ""
    items = "".join(f"<li>{_esc(f.splitlines()[0][:200])}</li>" for f in block_level[:5])
    return (
        f'<section class="glass"><div class="warn red">'
        f'<b>⚠️ Run had failures.</b> Partial pulse. See footer for full list.'
        f'<ul style="margin-top:8px;padding-left:20px">{items}</ul>'
        f'</div></section>'
    )


# ── main ──────────────────────────────────────────────────────────────────────
def render_html(data: dict) -> str:
    today = data.get("today") or date.today().isoformat()
    generated = datetime.now().strftime("%Y-%m-%d %H:%M %Z").strip()
    body = (
        '<header>'
        f'<h1>X <em>Pulse</em></h1>'
        f'<div class="date">{_esc(today)}</div>'
        f'<div class="status-row">{_status_pills(data)}</div>'
        '</header>'
        + _warnings_block(data)
        + '<section class="glass glass-strong"><h2>Today\'s posting <em>decision</em></h2>'
        + _decision_block(data)
        + '</section>'
        + _mentions_block(data)
        + _own_block(data)
        + _kol_block(data)
        + _viral_block(data)
        + _drafts_block()
        + '<footer>'
        f'<pre>{_esc(data.get("cost_summary",""))}</pre>'
        f'<div class="gen">Generated {_esc(generated)} · regenerate with '
        '<code>python scripts/monitor.py</code></div>'
        '</footer>'
    )
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>X Pulse — {_esc(today)}</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Barlow:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
        f'<style>{CSS}</style></head><body><main>{body}</main></body></html>'
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_dashboard.py <pulse_data.json> [output.html]")
        return 2
    src = Path(sys.argv[1]).expanduser()
    data = json.loads(src.read_text())
    out = (
        Path(sys.argv[2]).expanduser() if len(sys.argv) > 2
        else Path.home() / "Documents" / "Last30Days" / f"x-pulse-{data.get('today', date.today().isoformat())}.html"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
