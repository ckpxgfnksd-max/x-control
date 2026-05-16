# x-control

**Manage your X account via Claude.** Daily pulse on your own engagement + KOL signals (posting velocity, viral posts), and approval-gated posting/replying via the official X API. Read-side is hybrid: official API for everything that touches your account, the bundled bird-search (cookies, free) for KOL reads — no third-party API gateway.

Algorithm-aware: risk markers and the OON-trap / author-diversity-decay warnings are derived from the open [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm) Rust source, not creator folklore.

## Design choices

| Concern | Choice | Why |
|---|---|---|
| Reads of your own account | Official X API, owned-reads tier ($0.001/resource) | Sanctioned, ~$2/mo, no credential exposure |
| Writes (post, reply, delete) | Official X API, OAuth 2.0 PKCE | Only safe path — refresh-token-only storage, scoped, revocable from x.com |
| KOL reads | bird-search via /last30days cookies (AUTH_TOKEN + CT0) | Free; reuses session you already have. No third-party gateway. Trade: no follower counts, no quote tree. |
| Posting flow | Local file queue + interactive CLI | No web UI, no daemon. Drafts as `.md` files = git-trackable, diff-able, editable |
| Token storage | `state/oauth_tokens.json` chmod 600 | Loopback OAuth callback; refresh rotates on every use |
| Credential setup | `scripts/setup_env.py` (hidden-input prompts) | No editor required; no shell-history leakage |

## What "manage your X account" includes (and doesn't)

✅ Reading your own tweets, engagement, mentions, follower count
✅ Reading KOL accounts' tweets and follower deltas
✅ Posting tweets and threads (approval-gated)
✅ Posting replies to mentions or specific tweets (approval-gated)
✅ Deleting tweets you posted via the tool

❌ Auto-likes, auto-follows, programmatic quote-tweets — **removed from self-serve official API in April 2026**. The pulse highlights candidate targets; click them manually on x.com.
❌ Autonomous posting. Every write requires an explicit `[a]pprove` keypress.

## Install

Requires Python 3.11+ and macOS or Linux. Tested on Python 3.13.

```bash
# Clone into Claude Code's skills dir (or anywhere you keep skills)
git clone https://github.com/<your_user>/x-control.git ~/.claude/skills/x-control
cd ~/.claude/skills/x-control

# Create venv + install deps
python3 -m venv .venv
.venv/bin/pip install httpx python-dotenv click pyyaml

# Copy KOL template (edit it later)
cp kol_list.example.md kol_list.md
```

## Setup (3 steps)

### 1. Confirm /last30days cookies are configured

KOL reads use the bundled `bird-search.mjs` that ships with [/last30days](https://github.com/<your_user>/last30days), authenticated via your existing X session cookies. If `~/.config/last30days/.env` already has `AUTH_TOKEN` and `CT0` set, you're done with step 1. If not, run /last30days's setup wizard first.

### 2. Create an X OAuth 2.0 app

Go to https://developer.x.com/en/portal/dashboard:

- Open your app → **Settings** → **User authentication settings** → **Edit**
- **App permissions:** Read and write
- **Type of App:** Confidential client *(this is what produces the Client Secret)*
- **Callback URI:** `http://127.0.0.1:8765/callback`
- **Website URL:** any valid URL
- **OAuth 2.0 scopes:** `tweet.read`, `tweet.write`, `users.read`, `offline.access`
- **Save** → return to **Keys and Tokens** → reveal **OAuth 2.0 Client ID** and **Client Secret**

### 3. Save credentials (the only supported path)

```bash
.venv/bin/python scripts/setup_env.py
```

Three hidden prompts (XAPI_API_KEY can be left blank in this build — see note below; OAuth Client ID; OAuth Client Secret). Pasted values are not echoed and never enter your shell history. The script atomically writes `~/.config/x-control/.env` with mode 0600.

> The XAPI_API_KEY field is legacy. The current build uses bird-search instead of xapi.to. You can leave the field blank, or remove it from `setup_env.py`'s FIELDS list.

### 4. Run OAuth and verify

```bash
.venv/bin/python scripts/auth.py           # browser opens, you consent
.venv/bin/python scripts/monitor.py --dry-run
.venv/bin/python scripts/monitor.py --skip-kols
.venv/bin/python scripts/monitor.py        # full pulse
```

Output lands at `~/Documents/Last30Days/x-pulse-YYYY-MM-DD.md`.

## Daily flow

```
                                ┌── kol_list.md (your handle + N KOLs)
                                │
   morning cron ────────▶  monitor.py
                                │
   x-pulse-YYYY-MM-DD.md  ◀────┘
                                │
                                │  ↳ feeds your content brief skill
                                │
   throughout the day ──▶  drafts land in queue/pending/  (as YAML+text files)
                                │
   approve.py  ◀──── you, anytime ────▶ official X API ──▶ tweet shipped
                                │
   queue/posted/<id>.md captures tweet_id for tomorrow's owned-read engagement check
```

## Commands

| Command | What it does |
|---|---|
| `python scripts/setup_env.py` | Interactive credential setup (default path; no editor) |
| `python scripts/auth.py` | One-time OAuth 2.0 setup (opens browser) |
| `python scripts/monitor.py` | Generate today's pulse |
| `python scripts/monitor.py --dry-run` | Print planned calls, no network |
| `python scripts/monitor.py --skip-kols` | Own-account section only (no xapi.to) |
| `python scripts/monitor.py --only @handle` | Limit KOL fan-out to one handle |
| `python scripts/approve.py` | Interactive draft approval → post via OAuth |
| `python scripts/approve.py --list` | Show pending drafts without acting |
| `python scripts/approve.py --delete <tweet_id>` | Undo a published tweet |
| `python scripts/serve.py` | Host the dashboard at http://localhost:8787 (cbti-style HTML, with refresh button) |

## Dashboard

Every `monitor.py` run also writes `~/Documents/Last30Days/x-pulse-YYYY-MM-DD.html` — a single self-contained HTML file in the [cbti.club](https://cbti.club) design system (Instrument Serif + Barlow + JetBrains Mono on black, liquid-glass cards, film grain).

Open directly: `open ~/Documents/Last30Days/x-pulse-$(date +%F).html`

Or host locally with a stable URL:

```bash
.venv/bin/python scripts/serve.py
# → http://localhost:8787  (auto-opens browser)
```

The local server injects a refresh button that re-runs `monitor.py` on click. To auto-start on login, install the launchd template at `scripts/launchd.plist.template` — see SKILL.md for the one-liner.

## Risk markers in the approval CLI

Inspired by what the [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm) source explicitly treats as negative-feedback signals (mute, block, report, "not interested"):

| Marker | Why it matters |
|---|---|
| `engagement_bait` | "RT if you agree" / "comment yes" — high mute risk |
| `callout_named_account` | `@x is wrong/lying/cooked` — high block-by-fans risk |
| `ai_slop_openers` | "Let me explain" / "Here's the thing" — high "not interested" risk |
| `em_dash_overuse` | 3+ em-dashes in one tweet — AI-generation tell |
| `emoji_spam` | 5+ emojis in one tweet — shill signal |
| `numbered_list_in_one_tweet` | Bullet-list-as-tweet pattern — reads as slop |
| `price_target` / `guarantee_lang` / `shill_keywords` / `dm_solicitation` | Crypto-specific shill patterns |
| `contains_url_$0.20_per_post` | URL inclusion → 13× cost on post |

Plus a **burst warning** at draft time: if ≥2 standalone posts shipped in the last 4h, the CLI warns about `AuthorDiversityDecay` penalty risk. Threads are exempt (one author event).

## Cost (typical month)

| Item | Volume | Rate | Cost |
|---|---|---|---|
| Own posts | 5/day × 30 | $0.015 | $2.25 |
| Own replies | 3/day × 30 | $0.015 | $1.35 |
| Owned reads | 60/day × 30 | $0.001 | $1.80 |
| Mentions | 20/day × 30 | $0.010 | $6.00 |
| **Official subtotal** | | | **~$11.40** |
| KOL reads (bird-search via cookies) | unlimited | $0 | $0 |
| **Total** | | | **~$11/mo** |

Hardcap enforced via `MAX_DAILY_API_SPEND_USD` in `.env` (applies to the official side only — bird-search isn't metered).

## Security model

- **OAuth refresh token** is the only credential that can post on your behalf. It's stored at `state/oauth_tokens.json` (mode 0600, never committed). Revoke anytime from x.com → Settings → Connected Apps.
- **X session cookies** (AUTH_TOKEN + CT0) live in `~/.config/last30days/.env`, read by the bundled bird-search. Never sent anywhere off-machine. Rotate by re-running /last30days's cookie setup.
- **Approval flow** is the safety rail against bad posts: even an autonomous Claude session in your terminal can't ship a tweet without your `[a]pprove` keypress.
- **Cost cap** (`MAX_DAILY_API_SPEND_USD`) aborts mid-run if exceeded, defending against runaway loops.
- All credential-bearing files use atomic write + `chmod 600`.

## License

[Apache License 2.0](LICENSE) — Chase Wang, 2026.

## Related

- [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm) — the source the algorithm-aware risk markers are derived from
- [last30days](https://github.com/<your_user>/last30days) — ships the bird-search bundle this skill calls for KOL reads
- [x-brief](https://github.com/ckpxgfnksd-max/x-brief) — the daily content brief skill this pulse feeds into
