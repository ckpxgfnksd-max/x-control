---
name: x-control
description: Daily X pulse (own engagement + mentions + KOL signals) and approval-gated posting/replying via the official X API. Use when the user says "x pulse", "x control", "x dashboard", "check my X", "approve tweets", "post to X", "reply to mentions", "what should I post", "x engagement check", "did my tweet flop", or "draft a thread for X". Surfaces algorithm-aware warnings (OON-trapped tweets, AuthorDiversityDecay burst, negative-feedback risk markers) grounded in the open xai-org/x-algorithm Rust source. Hybrid stack: official X API (OAuth) for own account + writes; bundled bird-search (cookies) for KOL reads — no third-party gateway.
---

# x-control

## What this skill produces

**Daily pulse file** at `~/Documents/Last30Days/x-pulse-YYYY-MM-DD.md`:

1. **Your account section** (official X API, owned-reads): top 3 tweets last 24h by impressions with engagement counts and top reply texts. Flags **OON-trapped tweets** (replies ≥3 but likes ≤1 — argument tree with no in-network amplification, structurally suppressed by `OON_WEIGHT_FACTOR`). Flags **burst windows** (≥4 standalone posts in 24h — `AuthorDiversityDecay` penalty risk). Lists unanswered mentions ranked by author reach.
2. **KOL posting velocity** (bird-search via your last30days cookies): tweets/24h per KOL with day-over-day delta and ratio; flags KOLs whose posting rate jumped ≥1.5× and +3 tweets (attention shift / something brewing).
3. **Viral KOL posts** (bird-search): tweets in last 24h exceeding ≥500 likes OR ≥100 replies. (Bird does not expose quote counts or follower counts, so those signals are out of scope.)

**Post queue** at `queue/pending/` — markdown drafts with YAML frontmatter. An interactive CLI walks each draft, flags algorithm-aware risks (engagement bait, callouts of named accounts, AI-slop openers, em-dash overuse, emoji spam, URL inclusion, burst warning if you posted ≥2 standalone tweets in the last 4h), and on `[a]pprove` posts via the official API.

## Success criteria

- Pulse generates daily before your brief workflow runs
- Day-2 onward shows non-zero follower deltas (state persistence works)
- Approval CLI never auto-posts; every write requires explicit `[a]pprove` keypress
- xapi.to outage does NOT block the own-account section (graceful degradation)
- Total monthly spend < your `MAX_DAILY_API_SPEND_USD × 30` cap

## Constraints (do NOT cross)

- **Account credentials never leave your machine.** OAuth 2.0 refresh tokens stored locally (mode 0600) for posting; bird-search uses the AUTH_TOKEN/CT0 cookies you already configured for /last30days, also local. No third-party gateway ever sees your auth.
- **No autonomous posting in Phase 1.** Every write goes through `approve.py` with human keypress confirmation. `--auto` flag exists for batch approval but is documented as advanced use.
- **No auto-likes, auto-follows, or quote-tweets.** Self-serve official API removed these April 2026. Pulse highlights candidate targets; users click manually.
- **No abstraction layer.** Two concrete clients (`official.py`, `xapi.py`). Do not introduce a "provider" interface "in case we swap."
- **Cost hardcap.** `MAX_DAILY_API_SPEND_USD` in `.env` aborts the run if exceeded mid-pulse.
- **No retry-forever.** Bounded backoff (5 attempts), then fail loud into the digest footer.

## How to invoke

| Command | What it does |
|---|---|
| `python scripts/setup_env.py` | Interactive credential setup (hidden input, atomic write, chmod 600). Default path. |
| `python scripts/auth.py` | One-time OAuth 2.0 setup (opens browser, captures tokens) |
| `python scripts/monitor.py` | Generate today's pulse |
| `python scripts/monitor.py --dry-run` | Print planned calls, no network |
| `python scripts/monitor.py --skip-kols` | Own-account section only (no xapi.to) |
| `python scripts/monitor.py --only @handle` | Limit KOL fan-out to one handle |
| `python scripts/approve.py` | Interactive draft approval → post via OAuth |
| `python scripts/approve.py --list` | Show pending drafts without acting |
| `python scripts/approve.py --delete <tweet_id>` | Undo a published tweet |
| `python scripts/serve.py` | Host the dashboard locally at http://localhost:8787 (Ctrl-C to stop) |
| `python scripts/serve.py --no-open 8000` | Same, custom port, don't auto-open browser |

## Local dashboard

`scripts/serve.py` runs a tiny stdlib HTTP server on 127.0.0.1 (never exposed off-machine). Routes:
- `/` → latest dashboard, with an injected "↻ Regenerate now" pill
- `/YYYY-MM-DD` → that day's dashboard
- `/YYYY-MM-DD.md` → that day's raw markdown
- `/archive` → JSON list of available pulses
- `/healthz` → "ok"
- `POST /regenerate` → runs monitor.py, returns `{"ok":true}` on success

### Auto-start at login (optional)

```bash
sed "s|HOME_DIR_PLACEHOLDER|$HOME|g" \
    ~/.claude/skills/x-control/scripts/launchd.plist.template \
    > ~/Library/LaunchAgents/club.cbti.x-control-dashboard.plist
launchctl load ~/Library/LaunchAgents/club.cbti.x-control-dashboard.plist
open http://localhost:8787
```

Stop: `launchctl unload ~/Library/LaunchAgents/club.cbti.x-control-dashboard.plist`. Logs at `/tmp/x-control-dashboard.{out,err}.log`.

## Initial setup (one-time)

1. **Confirm /last30days is configured.** KOL reads use the bundled bird-search via your existing X session cookies. If `~/.config/last30days/.env` already has `AUTH_TOKEN` and `CT0` (set up by /last30days's wizard), you're done with step 1. If not, run /last30days's setup first.
2. **Create an X OAuth 2.0 app** at https://developer.x.com/en/portal/dashboard:
   - Open your app → **Settings** → **User authentication settings** → Edit
   - App permissions: **Read and write**
   - Type of App: **Confidential client** (this is what produces the Client Secret)
   - Callback URI: `http://127.0.0.1:8765/callback`
   - Website URL: any valid URL (e.g. `https://x.com/<your_handle>`)
   - OAuth 2.0 scopes: `tweet.read`, `tweet.write`, `users.read`, `offline.access`
   - Save → return to **Keys and Tokens** → reveal **OAuth 2.0 Client ID** and **Client Secret**
3. **Save credentials** (the only supported path — no editor required):
   ```bash
   python scripts/setup_env.py
   ```
   Hidden-input prompts for the OAuth Client ID + Client Secret. (The XAPI_API_KEY field is legacy and can be left blank — the current build uses bird-search instead.) Writes `~/.config/x-control/.env` atomically, mode 0600.
4. **Run OAuth flow** (browser opens for consent, tokens persist to `state/oauth_tokens.json` mode 0600):
   ```bash
   python scripts/auth.py
   ```
5. **Edit your KOL list.** Copy template and edit:
   ```bash
   cp kol_list.example.md kol_list.md
   ```
   The `own` row must have your handle. Add / remove KOLs as you like.
6. **Verify with dry-run, then real runs:**
   ```bash
   python scripts/monitor.py --dry-run                  # config check
   python scripts/monitor.py --skip-kols                # OAuth + own data only
   python scripts/monitor.py --only @<some_kol_handle>  # one KOL via bird-search
   python scripts/monitor.py                            # full pulse
   ```

## Phase 2 — likes / follows / quote-tweets

Self-serve official API removed these endpoints in April 2026. The pulse highlights candidate targets in the "Viral KOL posts" and "Unanswered mentions" sections so you can click them on x.com. If you ever want automation, the plan file's Phase 2 section lays out the three options (manual / browser automation / wait for X). Recommendation is start manual, revisit after 30 days of pulse data.
