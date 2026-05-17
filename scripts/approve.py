#!/usr/bin/env python3
"""Interactive approval CLI for pending drafts. Posts via official X API."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import queue                                        # noqa: E402
from scripts import signals                                      # noqa: E402
from scripts import tracker                                      # noqa: E402
from scripts.cost import CostTracker                             # noqa: E402
from scripts.clients.official import OfficialXClient             # noqa: E402

# Hard caps per algo: AuthorDiversityDecay exponential decay > 3 standalones/24h.
HARD_CAP_STANDALONES_24H = 3
HARD_CAP_REPLIES_24H = 2

ENV_PATH = Path.home() / ".config" / "x-control" / ".env"

# ANSI shortcuts
def _red(s: str) -> str: return f"\033[31m{s}\033[0m"
def _green(s: str) -> str: return f"\033[32m{s}\033[0m"
def _yellow(s: str) -> str: return f"\033[33m{s}\033[0m"
def _dim(s: str) -> str: return f"\033[2m{s}\033[0m"
def _bold(s: str) -> str: return f"\033[1m{s}\033[0m"


def _show(d: queue.Draft, posted_4h: int) -> None:
    tweets = d.tweets
    fm = d.frontmatter
    print()
    print(_bold(f"── draft: {d.path.name}"))
    print(_dim(
        f"  type={d.kind}  target={fm.get('target_time') or '—'}  "
        f"reply_to={d.in_reply_to or '—'}  url_count={fm.get('url_count', 0)}"
    ))
    # Surface authoring-intent metadata so the user can see what targeting
    # they declared. Empty fields are skipped.
    intent_bits = []
    if d.topic_tags:
        intent_bits.append(f"tags={','.join(d.topic_tags)}")
    if d.angle_type:
        intent_bits.append(f"angle={d.angle_type}")
    if d.audience_pool:
        intent_bits.append(f"pool={d.audience_pool}")
    if d.format_goal:
        intent_bits.append(f"goal={d.format_goal}")
    if d.experiment_label:
        intent_bits.append(f"exp={d.experiment_label}")
    if intent_bits:
        print(_dim("  intent: " + "  ".join(intent_bits)))
    risks = d.risk_markers()
    if risks:
        print(_red("  risks: " + ", ".join(risks)))
    # Author-diversity-decay warning. A thread is ONE author event so it doesn't
    # add to the count; only standalone posts do.
    is_thread = len(tweets) > 1
    if not is_thread and posted_4h >= 2:
        print(_yellow(
            f"  burst warning: {posted_4h} standalone posts in last 4h — "
            "AuthorDiversityDecay penalty likely. Consider deferring or threading."
        ))
    if is_thread:
        print(_yellow(f"  (thread, {len(tweets)} tweets — counts as one author event)"))

    # ── impression-lift signal panel (mirrors ranking_scorer.rs head structure)
    own_topics = set(tracker.topic_mix(hours=24 * 30).keys())
    panel = signals.score_draft(
        d.body,
        tweet_count=len(tweets),
        frontmatter=fm,
        own_topics=own_topics,
        risk_markers=risks,
    )
    print()
    print(_dim("  impression-lift signals (per ranking_scorer.rs heads):"))
    label_w = max(len(s.name) for s in panel)
    for s in panel:
        if s.name == "neg-feedback-risk":
            tag = signals.neg_label(s.score)
            color = _red if tag == "HIGH" else (_yellow if tag == "MED" else _green)
            print(f"    {s.name:<{label_w}}  {color(tag):<22}  {_dim(s.reason)}")
        else:
            bar = signals.bars(s.score)
            print(f"    {s.name:<{label_w}}  {bar:<5}  {_dim(s.reason)}")
    print()
    for i, t in enumerate(tweets):
        cc = len(t)
        color = _red if cc > 280 else (_yellow if cc > 260 else _green)
        prefix = f"  [{i + 1}/{len(tweets)}] {color(f'({cc}/280)')} "
        first = True
        for line in t.split("\n"):
            print(prefix + line if first else "  " + " " * (len(prefix) - 2) + line)
            first = False
    print()


def _editor_edit(d: queue.Draft) -> None:
    editor = os.environ.get("EDITOR") or shutil.which("nano") or shutil.which("vim") or "vi"
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tf:
        tf.write(d.body)
        tmp = Path(tf.name)
    try:
        subprocess.call([editor, str(tmp)])
        d.body = tmp.read_text()
        d.frontmatter["character_count"] = len(d.text)
        d.frontmatter["url_count"] = len(queue.URL_RE.findall(d.body))
        queue.write(d)
    finally:
        tmp.unlink(missing_ok=True)


def _post(d: queue.Draft, client: OfficialXClient) -> list[str]:
    """Post a draft (single tweet or thread). Returns list of tweet_ids."""
    ids: list[str] = []
    in_reply_to = d.in_reply_to
    for tweet_text in d.tweets:
        if len(tweet_text) > 280:
            raise ValueError(f"tweet exceeds 280 chars ({len(tweet_text)}): {tweet_text[:50]}…")
        result = client.post(tweet_text, in_reply_to=in_reply_to)
        tid = result.get("id")
        if not tid:
            raise RuntimeError(f"post returned no id: {result}")
        ids.append(tid)
        in_reply_to = tid  # next tweet replies to this one (thread)
    return ids


def _approve_one(
    d: queue.Draft, client: OfficialXClient, auto: bool, override: bool = False
) -> str:
    """Returns 'approved' | 'rejected' | 'skipped' | 'quit' | 'edited' | 'capped'."""
    posted_4h = queue.posted_in_last(4)
    _show(d, posted_4h)

    # ---- Hard caps (algo-aligned) -------------------------------------------
    is_reply = bool(d.in_reply_to) or (
        len(d.tweets) == 1 and d.tweets[0].lstrip().startswith("@")
    )
    is_thread = len(d.tweets) > 1
    standalones_24h = tracker.standalone_count_24h()
    replies_24h = tracker.reply_count_24h()

    if not is_thread:  # threads = one author event, never capped
        if not is_reply and standalones_24h >= HARD_CAP_STANDALONES_24H and not override:
            print(_red(
                f"  HARD CAP: {standalones_24h} standalones in last 24h "
                f"(limit {HARD_CAP_STANDALONES_24H}). AuthorDiversityDecay penalizes the next one."
            ))
            print(_dim("  Override with `python scripts/approve.py --override` (acknowledge the penalty)."))
            print(_yellow("  Better: thread your next idea instead, or reply from your mentions queue."))
            return "capped"
        if is_reply and replies_24h >= HARD_CAP_REPLIES_24H and not override:
            print(_red(
                f"  HARD CAP: {replies_24h} replies in last 24h "
                f"(limit {HARD_CAP_REPLIES_24H}). Reply quota spent."
            ))
            print(_dim("  Override with `--override` if this reply is high-leverage (e.g. >50k-follower mention)."))
            return "capped"
    if auto:
        choice = "a"
    else:
        try:
            choice = input("  [a]pprove  [r]eject  [e]dit  [s]kip  [q]uit > ").strip().lower()
        except EOFError:
            return "quit"
    if choice in ("q", "quit"):
        return "quit"
    if choice in ("s", "skip", ""):
        return "skipped"
    if choice in ("e", "edit"):
        _editor_edit(d)
        return "edited"
    if choice in ("r", "reject"):
        reason = input("  reason (optional): ").strip() or "manual"
        queue.archive(d, "rejected", {"rejection_reason": reason})
        print(_yellow(f"  → rejected ({reason})"))
        return "rejected"
    if choice in ("a", "approve", "y", "yes"):
        risks = d.risk_markers()
        if risks and not auto:
            confirm = input(_red(f"  RISKS: {', '.join(risks)}. Post anyway? [y/N] ")).strip().lower()
            if confirm not in ("y", "yes"):
                print(_dim("  → skipped"))
                return "skipped"
        try:
            ids = _post(d, client)
        except Exception as e:
            print(_red(f"  POST FAILED: {e}"))
            return "skipped"
        first_id = ids[0]
        url = f"https://x.com/i/web/status/{first_id}"
        # Record the ship for the weekly tracker (powers digest gap detection
        # + S19/S20 angle-diversity / experiment-maturity suggestions).
        ship_event = tracker.record_ship(
            tweet_id=first_id, tweets=d.tweets, is_reply=is_reply,
            topic_tags=d.topic_tags,
            angle_type=d.angle_type,
            audience_pool=d.audience_pool,
            format_goal=d.format_goal,
            experiment_label=d.experiment_label,
        )
        queue.archive(d, "posted", {
            "tweet_id": first_id,
            "tweet_ids": ids,
            "tweet_url": url,
            "format": ship_event["format"],
            "lang": ship_event["lang"],
        })
        print(_green(
            f"  → posted {url} ({len(ids)} tweet{'s' if len(ids) > 1 else ''}) "
            f"[{ship_event['format']}/{ship_event['lang']}]"
        ))
        return "approved"
    print(_dim(f"  unknown choice: {choice!r}"))
    return "skipped"


def main() -> int:
    ap = argparse.ArgumentParser(description="Approve and post pending drafts")
    ap.add_argument("--list", action="store_true", help="show pending drafts and exit")
    ap.add_argument("--auto", action="store_true", help="approve everything (advanced — use with care)")
    ap.add_argument("--delete", help="delete a published tweet by id")
    ap.add_argument("--override", action="store_true",
                    help="bypass hard caps (standalones ≥3/24h, replies ≥2/24h) for this run")
    args = ap.parse_args()

    load_dotenv(ENV_PATH)

    if args.delete:
        cost = CostTracker()
        client = OfficialXClient(
            client_id=os.environ.get("X_OAUTH_CLIENT_ID", ""),
            client_secret=os.environ.get("X_OAUTH_CLIENT_SECRET", ""),
            cost=cost,
        )
        try:
            ok = client.delete(args.delete)
            print(_green(f"deleted={ok}  tweet_id={args.delete}"))
        finally:
            client.close()
        return 0 if ok else 1

    drafts = queue.list_pending()
    if args.list:
        if not drafts:
            print("no pending drafts")
            return 0
        for d in drafts:
            cc = len(d.text)
            risks = d.risk_markers()
            risk_str = _red(f"  risks={','.join(risks)}") if risks else ""
            print(f"  {d.path.name}  type={d.kind}  ({cc}/280){risk_str}")
        return 0

    if not drafts:
        print("no pending drafts")
        return 0

    cost = CostTracker()
    client = OfficialXClient(
        client_id=os.environ.get("X_OAUTH_CLIENT_ID", ""),
        client_secret=os.environ.get("X_OAUTH_CLIENT_SECRET", ""),
        cost=cost,
    )
    counts = {"approved": 0, "rejected": 0, "skipped": 0, "edited": 0, "capped": 0}
    try:
        for d in drafts:
            # Edit loop: stay on the same draft after an edit
            while True:
                result = _approve_one(d, client, auto=args.auto, override=args.override)
                if result == "quit":
                    print(cost.summary())
                    return 0
                if result == "edited":
                    d = queue.load(d.path)  # reload after edit
                    continue
                counts[result] = counts.get(result, 0) + 1
                break
    finally:
        client.close()
    print()
    print(f"summary: {counts}")
    print(cost.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
