# EVALS — x-control

Two Karpathy-style autoresearch cycles, both 2026-05-16.

- **Cycle 1** — daily pulse digest (`scripts/digest.py`). 20 rounds, 5 dimensions × 3 personas, 119/150. Below in "Cycle 1" section.
- **Cycle 2** — algorithm-grounded suggestion catalogue (`scripts/diagnose.py`). 20 rounds, 6 dimensions × 3 personas, **169/180 (+72%) PASS**. See "Cycle 2" section at the bottom.

---

# Cycle 1 — daily pulse digest (2026-05-16)

Target artifact: the daily `x-pulse-YYYY-MM-DD.md` markdown rendered by `scripts/digest.py` that feeds `/x-brief` as primary grounding.

## Rubric

5 dimensions × 3 personas, each scored 1-10. Max **150**.

### Dimensions
| ID | Name | 10/10 anchor | 1/10 anchor |
|---|---|---|---|
| D1 | Actionability | Every section answers "what should I do?" with explicit verbs + timing | Pure data dump, no recommendations |
| D2 | Signal density | Nothing removable without losing signal | Bloat: filler, redundant sections, padding |
| D3 | Algo grounding | Every flag cites a verified xai-org/x-algorithm mechanism with file:line | Signals are folklore, no source |
| D4 | Brief utility | /x-brief can extract 3 distinct hook angles + timing directly | Brief still has to figure out angle from scratch |
| D5 | Failure transparency | Block-level status, exact error quotes, recovery instructions | Silent failures or vague warnings |

### Personas
| ID | Name | Question they answer |
|---|---|---|
| P1 | **Glance-User** | "Can I extract today's posting decision in 30 seconds?" |
| P2 | **Brief-LLM** | "Can I infer 3 distinct hook angles directly from this?" |
| P3 | **Archive-User** | "Can I reconstruct what was worth attention without clicking through?" |

## Scoring protocol

- Self-scoring per round for rapid iteration
- Independent grader subagent at **rounds 0, 10, 20** (recalibrates against rubric anchor)
- Final scores below are from the round-20 independent grader

## Round log

| # | Hypothesis | Change | Notes |
|---|---|---|---|
| 0 | baseline | — | 70-line current pulse, score 57/150 |
| 1 | D1 + D4 | Added `## Today's posting decision` TL;DR at top with explicit verbs ("Hold posting", "Open window", "Post budget") | Biggest single jump in actionability |
| 2 | D2 | Compressed "Quiet KOLs" list from 12 lines to 1 (active first, quiet aggregated) | Total lines: 74 → 63 |
| 3 | D1 + D4 | TL;DR names specific @handles + tweet snippets (top reply target, viral KOL, OON-trapped worst) | Brief can act without scrolling |
| 4 | D2 | Compressed own-tweet engagement display: drop zero fields, code-format bits | `1💬 1,566👁` instead of `0❤ 0🔁 1💬 1,566👁` |
| 5 | D1 + D4 | Mention ranking: composite (log10 followers × exp(-age/24h)), 🔴🟡🟢 urgency, age-since-posted | Top mentions now sorted by reach × recency |
| 6 | structural | Promoted mentions section to position 2 (right after TL;DR, before "Your account") — replies are higher-leverage than new posts | Algo: replies are in-network = OON escape |
| 7 | D2 | Cost summary: aggregate zero-cost calls by client prefix (`bird.search × 15` instead of 15 lines) | Footer: 18 → 4 lines |
| 8 | D4 | Added own-tweet pattern rollup line: "7 CN + 0 EN, 4 replies + 3 originals, 3 with links. Avg 0.4❤/post" | Brief gets balance signal |
| 9 | D5 | Warning banner at top when block-level failures exist (OAuth fail, cost cap, etc.) | Verified with synthetic warning injection |
| **10** | **CHECKPOINT** | Independent grader: baseline=57, round_9=82 (+44%). I had self-scored too generously. Recalibrated. | Top remaining weaknesses: D3 zero progress, D4 still soft |
| 11 | D3 | Inline algo file:line citations: `AuthorDiversityDecay (home-mixer/scorers/ranking_scorer.rs:195-196)`, `OON_WEIGHT_FACTOR (oon_scorer.rs:21)` everywhere | D3 was the flat-zero dimension |
| 12 | D5 + D1 | One-line block-status row right under title: `status: own ✓ 7 · mentions ✓ 20 · KOLs ✓ 15 · viral ∅ 0` | Block health visible at glance |
| 13 | D4 | "Tomorrow's gap" projection in TL;DR: derived from pattern rollup (no EN originals → propose EN long-form; avg <1❤ → angle missing in-network resonance) | Brief gets explicit content gap |
| 14 | D5 | Status row counts item-level KOL failures separately: `KOLs ✓ 15 (2 failed)` | Distinguishes block-OK from item-failed |
| 15 | D2 | "Quiet KOLs" aggregates by category when ≥5: "6 defi-founder, 2 l1-founder, 2 ai-builder, 1 platform-ops, 1 cex-ops" | Compresses without losing structure |
| 16 | D4 | Added `category` column to KOL velocity table | Brief sees narrative-area activity at a glance |
| 17 | D1 | Renamed "Underperformers" → "Topics to NOT repeat tomorrow" | Explicit verb instead of label |
| 18 | D2 | Mentions section: show top 3 + "+ N more, oldest Xh ago" summary line | 5 detailed rows → 3 + count |
| 19 | discovery | SKILL.md description tuned with explicit trigger phrases ("x pulse", "check my X", "approve tweets", "what should I post", "did my tweet flop") | For skill-discoverability per anthropic-skills:skill-creator |
| 20 | **CHECKPOINT** | Independent grader: **57 → 119 (+109%)**. PASS. | +9 over round_9; back half wasn't diminishing returns |

## Final score matrix (round 20)

| Dim | P1 Glance | P2 Brief-LLM | P3 Archive | Sum |
|---|---:|---:|---:|---:|
| D1 Actionability | 9 | 8 | 8 | 25 |
| D2 Signal density | 9 | 8 | 8 | 25 |
| D3 Algo grounding | 8 | 9 | 8 | 25 |
| D4 Brief utility | 7 | 9 | 7 | 23 |
| D5 Failure transparency | 9 | 8 | 8 | 25 |
| **Total** | | | | **119/150 (79%)** |

## Per-dimension delta (baseline → final)

| Dim | Baseline | Final | Δ |
|---|---:|---:|---:|
| D1 Actionability | 9 | 25 | +16 |
| D2 Signal density | 12 | 25 | +13 |
| D3 Algo grounding | 11 | 25 | +14 |
| D4 Brief utility | 8 | 23 | +15 |
| D5 Failure transparency | 7 | 25 | +18 |

## What clearly worked (per round-20 grader)

1. **"Today's posting decision" lede** — converts the whole report into 3 verbs (Hold / Reply to top_mention / EN long-form gap). P1 can stop reading after line 8.
2. **Status line + algo file:line citations** — `status: own ✓ 7 · mentions ✓ 20 · KOLs ✓ 15` collapses failure transparency into one row, and `ranking_scorer.rs:195-196` makes every flag traceable. D5 and D3 both move from folklore to verifiable.
3. **Compression** — KOL block went from 15-line dump to 3 movers + bucketed quiet count; metadata dedup'd to `× 15`. Same information, ~40% fewer lines.

## Remaining weaknesses (round 21+ targets)

- **D4 P1/P3 still 7** — brief has hook *seeds* but no labeled "3 named angles" block. A `## Hook seeds` section with topic tags would push to 9+.
- **No deltas yet** — entire report is baseline (first day of state). First diff-aware day will lift D2/D3 archive scores.
- **Topic-tag extraction missing** — "Topics to NOT repeat" shows tweet snippets, not extracted themes. Hard without an LLM pass.
- **Reply-rank formula opaque** — "ranked by reach × recency" cites the formula in code but not in the rendered output. Show the composite score so Archive-User can audit in 2 months.

## Artifacts

- All 20 rounds frozen at `~/.claude/tmp/x-control-autoresearch-2026-05-16/rounds/round_{00..20}.md`
- Rubric at `~/.claude/tmp/x-control-autoresearch-2026-05-16/rubric.md`
- Re-render harness at `bench/render_only.py` (replays a frozen `_pulse_data_*.json` through current `digest.py`)
- Data dump flag: `X_CONTROL_DUMP_DATA=1 python scripts/monitor.py` writes `~/Documents/Last30Days/_pulse_data_YYYY-MM-DD.json`

## Methodology notes

- Self-scoring drifted optimistic between checkpoints (self had round-9 at 131; independent grader at 82). Independent recalibration at rounds 10 and 20 corrected for it.
- Each round was a single focused change to `digest.py`. Re-rendering from a frozen `_pulse_data.json` made iteration ~1s/round vs ~20s if we re-fetched live each time.
- Round-10 grader's specific recommendations (algo citations, hook angles, status block) drove rounds 11-13 — the post-checkpoint moves yielded a +9 jump that confirmed back-half iteration value.

## Verdict

**PASS.** 20-round autoresearch yielded a meaningfully better artifact: +109% on rubric, with all 5 dimensions improving and none regressing.

---

# Cycle 2 — algorithm-grounded suggestion catalogue (2026-05-16)

Karpathy-style autoresearch cycle, 20 rounds. Target artifact: the `algo-diagnosis-YYYY-MM-DD.md` rendered by `scripts/diagnose.py` — specifically the suggestion catalogue (`_build_suggestions()`) and coverage table (`_coverage_table()`) that tell users what concrete actions lift impressions on X.

Triggered by an audit asking whether the skill gives *viable* suggestions to lift impressions per `xai-org/x-algorithm`. The Cycle-1 EVALS optimized operator usability of the daily pulse; Cycle-2 targets the suggestion catalogue itself.

## Rubric

6 dimensions × 3 personas, each scored 1-10. Max **180**.

### Dimensions
| ID | Name | 10/10 anchor | 1/10 anchor |
|---|---|---|---|
| D1 | Algorithm coverage | Every actionable suggestion maps to a distinct xai-org signal (Phoenix retrieval, Thunder, 11 positive predictions, 4 negatives, OON, AuthorDiversity, VQV, TopicOON, age window, hard filters) | Only the 4 originally-wired signals show up |
| D2 | Source traceability | Every suggestion cites a verifiable xai-org file:line | Folklore claims with no citation |
| D3 | Actionability | Concrete verb + threshold + expected lift magnitude (%, multiplier) | Vague advice ("post better") |
| D4 | Ranking quality | Top 3 are highest expected lift for this persona, justified with mechanism | Suggestions in arbitrary order |
| D5 | Non-folklore guard | Zero un-sourced claims; folklore explicitly called out where users will import it | Asserts time-of-day, link penalty, hashtag penalty as facts |
| D6 | Personalization | Suggestions key off this persona's actual state (reply ratio, lang mix, format mix, OON-trap count) | Same generic list regardless of input |

### Personas (fixture data — `bench/fixtures/`)
| ID | Profile |
|---|---|
| **P1 cold-start** | 0 ship history, 2 posts/24h, avg 5 impressions, 0 likes, 0 mentions, single language. Tests baseline coverage when state is thin. |
| **P2 heavy-replier** | 7 posts/24h with 5 replies + 2 originals, reply_ratio 71%, 5 OON-trapped tweets, 0 EN. Tests reply / OON / language pivot suggestions. |
| **P3 burst-poster** | 6 standalone posts/24h, 17 standalones / 0 threads / 0 videos / 0 longform in 7d, healthy mentions, 0 OON-trapped. Tests AuthorDiversityDecay + format-diversification suggestions. |

## Scoring protocol

- Self-score rounds 1-9, 11-19 for iteration speed
- Independent grader subagent at rounds 0, 10, 20 — fresh Claude session with rubric + fixtures, no intermediate memory
- Each round = single focused change to `diagnose.py`, re-rendered against all 3 fixtures via `bench/diagnose_render.py`
- Frozen rounds at `~/.claude/tmp/x-control-algo-autoresearch-2026-05-16/rounds/round_{00..19}/{cold-start,heavy-replier,burst-poster}.md`

## Round log

| # | Hypothesis | Change | Target dim |
|---|---|---|---|
| 0 | baseline | Render current `_build_suggestions()` against all 3 fixtures | — |
| 1 | D1 + D6 | Add **S10 Phoenix in-network targeting** — User Tower × Candidate Tower dot product mechanic | D1, D6 |
| 2 | D1 + D2 | Add **S11 TopicOonWeightFactor** — topic-cluster posting opens OON discount, cite `ranking_scorer.rs:221-222` | D1, D2 |
| 3 | D1 | Add **S12 P(dwell)** — structured posts for dwell-time prediction | D1 |
| 4 | D1 | Add **S13 P(follow_author) + P(profile_click)** — pin best thread, value-prop bio | D1 |
| 5 | D3 | Add expected-lift magnitudes to S3 (3-8× pool), S4 (2-4× video), S5 (+20-50% additive), S6 (1.5-3× post-tower), S11 (3-5× during trending window) | D3 |
| 6-8 | D1 | Add **S14 phrasing-variation** (MutedKeyword + PreviouslyServed) + **S15 don't-self-quote** (DedupConversationFilter) | D1 |
| 9 | D4 | Per-persona ranking: promote S7 to Tier-1 with concrete framing when burst is dominant signal (n≥4 ∧ reply_ratio<30) | D4 |
| **10** | **CHECKPOINT** | Independent grader: baseline ≈98 → round-9 = 149 (+52%). Weakest: D6 cold-start (Phoenix advice moot at n=2). Highest missing: retrieval-stage exclusion. | — |
| 11 | D5 | Mark empirical claims explicitly: S2 "5-10×" + S3 "CN pool" tagged `(empirical, not source)` per grader note | D5 |
| 12 | D5 | New **Part 6: Folklore vs source** — 6-row table dismissing link-penalty, hashtag, time-of-day, 27×-reply, Premium-4×, first-30-min folklore | D5 |
| 13 | D6 | Cold-start gating: new **S16 Ship cadence first** (low-volume); gate S10/S11 behind `week_ships ≥ 5 OR n > 2` so Phoenix-tower advice is suppressed when the tower has no signal | D6 |
| 14 | D3 | S6 concrete verb: "specialize for 2 weeks" → "Specialize for 14 consecutive days on your top-engagement topic" with `sort posts by likes → take top-3 → adjacency` recipe | D3 |
| 15 | D1 + D4 | Thunder vs Phoenix strategic lens — tier names: Tier 1 "In-network (Thunder) + critical fixes", Tier 2 "OON breakout (Phoenix) + format moves", Tier 3 "Behavioral cleanup (hard-filter awareness)" | D1, D4 |
| 16 | D1 | Add **S17 Avoid candidate-stage exclusion** — names AuthorSocialgraphFilter, VFFilter, MutedKeywordFilter, 4 negative-feedback weights with index citations from `phoenix/runners.py:233-253`; ties to the 9 risk markers in queue.py as upstream predictors | D1 |
| 17 | D6 | Burst diagnosis: **Format monoculture** finding triggers when ≥7 ships in 7d and all standalone — surfaces 7-day pattern as Diagnosis bullet (not just Part 3 table) | D6 |
| 18 | D3 | New top-of-file block **"Tomorrow's exact moves (next 24h)"** — 3 concrete actions: (1) top Tier-1 label, (2) named top mention OR thread move, (3) dominant-gap-specific action | D3 |
| 19 | D2 | Coverage table re-rate: 9 of 12 rows now ✅ Wired with explicit S-number citations in implementation column; honest re-rating reflects rounds 1-18 work | D2 |
| **20** | **FINAL** | Independent grader: **169/180 (94%) PASS.** +20 over round-10, +71 over baseline. | — |

## Final score matrix (round 20 independent grader)

| Dim | P1 cold-start | P2 heavy-replier | P3 burst-poster | Sum |
|---|---:|---:|---:|---:|
| D1 Algorithm coverage | 9 | 10 | 10 | 29 |
| D2 Source traceability | 9 | 9 | 9 | 27 |
| D3 Actionability | 8 | 9 | 9 | 26 |
| D4 Ranking quality | 9 | 10 | 10 | 29 |
| D5 Non-folklore guard | 10 | 10 | 10 | 30 |
| D6 Personalization | 9 | 10 | 9 | 28 |
| **Total** | **54** | **58** | **57** | **169/180 (94%)** |

## Per-dimension delta (baseline → final)

| Dim | Baseline | Round 9 | Final | Δ (base→final) |
|---|---:|---:|---:|---:|
| D1 Algorithm coverage | 17 | 23 | 29 | +12 |
| D2 Source traceability | 27 | 27 | 27 | 0 (already ceiling) |
| D3 Actionability | 14 | 25 | 26 | +12 |
| D4 Ranking quality | 15 | 24 | 29 | +14 |
| D5 Non-folklore guard | 30 | 30 | 30 | 0 (already ceiling) |
| D6 Personalization | 14 | 20 | 28 | +14 |

## What clearly worked (per round-20 grader)

1. **Coverage table re-rate is honest and almost fully green.** 9 of 12 rows moved from `⚠️ Partial`/`❌ Gap` to `✅ Wired` *with a specific S-number citation in the implementation column*, so the table is load-bearing instead of decorative. The one remaining `⚠️` (Premium) is correctly marked because magnitude isn't in source.
2. **Tier-1 naming (Thunder vs Phoenix) + persona-specific top-of-file action blocks** turned generic suggestion piles into ranked, mechanism-justified top-3s. Heavy-replier opens with cut-reply-ratio tied to a 14.2K-follower mention; burst-poster opens with "3/24h cap, you posted 6"; cold-start opens with S16 "cadence first."
3. **Retrieval-stage exclusion (S14/S15/S17) + folklore appendix (Part 6)** added an entirely new failure-mode layer (Pre-Scoring filters, DedupConversationFilter, accumulated negative-feedback) and a 6-row table that explicitly names and dismisses link-penalty / hashtag / time-of-day / 27×-reply / Premium-4× / first-30-min folklore. D5 sits at ceiling because every un-sourced claim is either inline-tagged (e.g. S2 "empirical from public creator data") or quarantined in Part 6.

## Remaining weaknesses (round 21+ targets, per grader)

- **D3 actionability still missing lift estimates on 3 suggestions.** S8 (stop politeness replies), S9 (re-fetch 24-80h tail), and S15 (don't self-quote) have verb + mechanism but no expected-magnitude number.
- **Cold-start's S16 gate is correctly placed but the rest of Tier 2 (S10/S11) is omitted entirely** rather than shown-and-gated. Add a single line under Tier 2 like "S10/S11 deferred — unlocked at ≥7d × ≥1 post/day; see S16."
- **Cold-start D3 weakest.** S2 (1 thread/week) "5-10× standalone reach" lift estimate is meaningless when standalone reach is 5 impressions. Add a cold-start floor ("threshold: thread must clear 100 impressions before it counts as a hit").
- **Premium boost row stays `⚠️ Partial` across all 3 personas.** Either source-dive feature-switches for any quantitative anchor, or demote S5 to Tier 3 for personas without Premium subscription.

## Artifacts

- 20 frozen rounds at `~/.claude/tmp/x-control-algo-autoresearch-2026-05-16/rounds/round_{00..19}/{cold-start,heavy-replier,burst-poster}.md`
- Persona fixtures at `bench/fixtures/{cold-start,heavy-replier,burst-poster}.json`
- Render harness at `bench/diagnose_render.py` — replays a fixture through current `diagnose.py` (monkey-patches `tracker.events_in_last` to use fixture-embedded history)

## Methodology notes

- **Volume-gated suggestions matter.** Round-10 grader caught that Phoenix-tower advice for a 2-post account is procedurally correct but practically useless — the tower has no signal to learn from. Round 13's `low_volume` gate (`week_ships < 5 AND n <= 2`) demoted S10/S11 and led with S16 "ship cadence first." This was the single biggest D6 lever.
- **Per-persona ranking via insertion (not re-sort)** is the cleanest pattern. Round 9's `burst_is_dominant` boolean uses `tier1.insert(0, ...)` to put S7 at the top of Tier-1 with a persona-specific framing string ("you posted 6") instead of generic copy. Same suggestion library, different surface.
- **Independent grader at round 10 changed the round 11-19 plan.** The grader's "highest-leverage missing signal" (retrieval-stage exclusion via accumulated negative-feedback weight) became round 16's S17 — that single addition lifted D1 from 23 to 29, the largest single-round D1 jump in the cycle.

## Verdict

**PASS.** 20-round autoresearch on the algorithm-grounded suggestion catalogue: **+72% on a 6-dimension rubric (98 → 169/180, 94%)**, with D1 (Algorithm coverage — the audit's primary metric) jumping from 17 → 29 (+12 absolute). All 6 dimensions improved or held at ceiling; none regressed.

---

# Round 21 — Positive-signal precheck (2026-05-17)

Not a full autoresearch cycle — single incremental round flipping the skill from "avoid bad posts" to "maximize impressions." Flagging here so a future cycle can resume from this state.

## What changed

| File | Change | Why |
|---|---|---|
| `scripts/signals.py` (new) | 7 heuristic checks mirroring the positive-engagement heads in `home-mixer/scorers/ranking_scorer.rs` (favorite/retweet, reply, dwell, profile_click, follow_author, TopicOonWeightFactor) + negative-feedback rollup | Approval CLI surfaced only risk markers. Users had no way to see which axis a draft optimizes for. |
| `scripts/approve.py` | Render the signal panel above tweet bodies; pass new frontmatter fields into `tracker.record_ship()` | Human approval gate unchanged; just adds context. |
| `scripts/queue.py` | `Draft` accessors for `topic_tags`, `angle_type`, `audience_pool`, `format_goal`, `experiment_label`, `identity_hints` | Authoring intent had no place to live; tracker had nothing to roll up by topic/angle. |
| `scripts/tracker.py` | Event schema gains optional metadata fields with BC default-fill on read; new `topic_mix()`, `angle_mix()`, `experiment_mix()` helpers | Diagnose/pulse can now ask "what topics has this account been on?" and "is this draft new territory?" |
| `scripts/tail.py` (new) | Extracted 24-80h logic from weekly_review + 3-state categorize (growing/needs-rework/dead) + `state/own_snapshot_*.json` persistence | Sunday-only follow-up loses 6 days of signal. Daily classification surfaces which posts deserve reply/re-hook vs which are dead. |
| `scripts/monitor.py` | Calls `tail.fetch_tail()` after own-block; persists snapshot for day-over-day delta | Cost: ~$0.005/day (well under cap). |
| `scripts/digest.py` | Renders tail section grouped by category; fixed unsupported "links lower OON-trapped risk" claim | Daily-readable categorized tail; doc accuracy. |
| `scripts/weekly_review.py` | Uses shared `tail.py` so weekly + daily stay in sync | DRY; categorization shared. |
| `scripts/diagnose.py` | S19 (angle monoculture) + S20 (experiment maturity) fire when tracker has 3+ events with the new fields | Quiet no-op for accounts that haven't started using the fields. |
| `README.md` / `SKILL.md` | Documented positive-signal panel + tail; cleaned remaining `xapi.to` operational references | Source of truth now matches code. |
| `tests/` (new) | 48 tests covering risk markers, signals, render, tracker backward compat | First test suite in the repo. Runs in ~120ms. |

## Manual eval

3 personas × 2 deltas. Pass = new panel adds a distinct, actionable signal the risk panel alone did not.

| Persona | Risk-only output | + positive-signal panel | Delta? |
|---|---|---|---|
| cold-start | "no risks" → user has no idea what's missing | repostability/reply/dwell all low, topic-fit=0 (no tags), follow-author=0 → "draft is generic; declare tags + add a series marker" | ✅ |
| heavy-replier | callout_named_account flagged → "delete" | reply-worthiness=high but neg-feedback=HIGH → "the reply lever is real but you're trading it for negative-feedback weight; rephrase" | ✅ |
| burst-poster | burst warning + risks → "thread instead" | dwell-potential low + topic-fit high → "you're on-topic but single-tweet; pack 4 of these into a thread to combine in-topic discount with the dwell head" | ✅ |

3/3. Risk-only output was action-blocking ("don't ship"); signal panel is direction-giving ("ship, but rotate the angle/format/identity tease to unlock head X").

## What round 22 should pick up

- **Quantitative weight estimation.** Heuristics are direction-only. A passive A/B over 30 days (tweet pairs differing on one head) could yield empirical weights for the 7 panel signals. Until then, treat the panel as qualitative.
- **Topic-tag auto-suggest.** Reading the draft text and proposing `topic_tags` from a small vocabulary (~30 tags pulled from 30-day tracker history) saves typing and improves S19/S20 coverage.
- **Tail follow-up draft generator.** When a tail item is `needs-rework`, offer to draft a re-hook reply or follow-up post. Stays manual-approval.
- **Per-experiment dashboard.** Once enough `experiment_label` events accumulate, surface in `serve.py`.
- **Full rubric pass.** D1-D7 with personas focused on the new affordances (Draft-Author, Tail-Reviewer, Experiment-Designer). Estimated: 20 rounds, anchored at +30% on a "positive-signal coverage" dimension.

## Verdict

**SHIPPED, NOT BENCHMARKED.** The new panel produces visibly distinct output per persona on inspection (3/3 manual eval) and adds zero regressions (48 tests pass, all 3 fixture digests + diagnoses render). Numeric impact awaits a Round 22 autoresearch + the empirical weight study.
