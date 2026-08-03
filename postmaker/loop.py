"""The poll loop and per-topic orchestration.

State lives entirely in Discourse:
  - network tag present  -> that network's draft is ready (set by us when done)
  - hidden comment marker -> dedup / crash-recovery between create and tag
"""

import sys
import time

from . import render
from .discourse import Discourse
from .generate import GenError, generate
from .networks import STATS_MARKER, draft_marker


def log(msg: str) -> None:
    print(f"[postmaker] {msg}", flush=True)


def _own_raw(cfg, dc: Discourse, topic: dict) -> str:
    """Concatenated raw of comments authored by our api user (where markers live)."""
    posts = (topic.get("post_stream") or {}).get("posts") or []
    chunks = []
    for p in posts:
        if p.get("username") == cfg.api_username:
            chunks.append(dc.get_post_raw(p["id"]))
    return "\n".join(chunks)


def _ensure_tag(cfg, dc: Discourse, topic_id: int, tags: set[str], key: str) -> None:
    if key in tags:
        return
    tags.add(key)
    if not cfg.dry_run:
        dc.set_tags(topic_id, sorted(tags))


def process_topic(cfg, dc: Discourse, topic: dict) -> None:
    tid = topic["id"]
    title = topic.get("title") or topic.get("fancy_title") or ""
    tags = set(topic.get("tags") or [])
    keys = [n.key for n in cfg.networks]

    if set(keys).issubset(tags):
        return  # every network drafted already — nothing to do

    posts = (topic.get("post_stream") or {}).get("posts") or []
    if not posts:
        return
    first_post_id = posts[0]["id"]
    body = dc.get_post_raw(first_post_id)
    own_raw = _own_raw(cfg, dc, topic)

    # 1) reserved service comment, always right after the first post
    if STATS_MARKER not in own_raw:
        log(f"topic {tid}: creating service comment")
        if not cfg.dry_run:
            dc.create_post(tid, render.render_stats(cfg))
        own_raw += "\n" + STATS_MARKER

    # 2) one draft comment per network (whose draft isn't ready yet)
    for net in cfg.networks:
        if net.key in tags:
            continue
        if draft_marker(net.key) in own_raw:
            # comment exists but tag missing (interrupted last run) -> just tag
            log(f"topic {tid}: {net.key} draft exists, tagging")
            _ensure_tag(cfg, dc, tid, tags, net.key)
            continue
        log(f"topic {tid}: generating {net.key} draft")
        try:
            parts = generate(cfg, net, title, body)
        except GenError as e:
            log(f"topic {tid}: {net.key} generation failed: {e}")
            continue
        comment = render.render_draft(net, title, parts)
        if cfg.dry_run:
            log(f"topic {tid}: [dry-run] {net.key} ({len(parts)} part(s))\n{comment}")
            continue
        dc.create_post(tid, comment)
        _ensure_tag(cfg, dc, tid, tags, net.key)


def run_once(cfg, dc: Discourse) -> None:
    for t in dc.topics_with_tag(cfg.tag):
        if cfg.category_id is not None and t.get("category_id") != cfg.category_id:
            continue
        try:
            process_topic(cfg, dc, dc.get_topic(t["id"]))
        except Exception as e:  # one bad topic shouldn't kill the pass
            log(f"topic {t.get('id')}: error: {e}")


def run(cfg) -> None:
    dc = Discourse(cfg.url, cfg.api_key, cfg.api_username)
    scope = f"tag='{cfg.tag}'"
    if cfg.category_id is not None:
        scope += f" category={cfg.category_id}"
    log(
        f"up. {scope} every {cfg.poll_interval}s, model={cfg.claude_model}, "
        f"networks={[n.key for n in cfg.networks]}, dry_run={cfg.dry_run}"
    )
    while True:
        try:
            run_once(cfg, dc)
        except Exception as e:
            log(f"pass error: {e}")
        time.sleep(cfg.poll_interval)
