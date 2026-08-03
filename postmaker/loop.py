"""The poll loop and per-topic orchestration.

State lives entirely in Discourse TAGS — we never parse comment bodies:
  - `<key>-draft`      -> draft ready (set here, after posting)
  - `<key>-published`  -> published (set by the publisher tool)
Templates are presentation only; nothing functional depends on their text.
"""

import time

from . import render
from .discourse import Discourse
from .generate import GenError, generate
from .networks import draft_tag, published_tag


def log(msg: str) -> None:
    print(f"[postmaker] {msg}", flush=True)


def _set_tag(cfg, dc: Discourse, topic_id: int, tags: set[str], key: str) -> None:
    if key in tags:
        return
    tags.add(key)
    if not cfg.dry_run:
        dc.set_tags(topic_id, sorted(tags))


def _handled(tags: set[str], key: str) -> bool:
    """A network is handled once its draft is ready or it's published."""
    return draft_tag(key) in tags or published_tag(key) in tags


def process_topic(cfg, dc: Discourse, topic: dict) -> None:
    tid = topic["id"]
    title = topic.get("title") or topic.get("fancy_title") or ""
    tags = set(topic.get("tags") or [])

    to_draft = [n for n in cfg.networks if not _handled(tags, n.key)]
    if not to_draft:
        return  # every network drafted or published already

    posts = (topic.get("post_stream") or {}).get("posts") or []
    if not posts:
        return
    body = dc.get_post_raw(posts[0]["id"])

    # Reserved service comment: create once, on the first pass that drafts this
    # topic (i.e. when it carries none of our -draft tags yet).
    first_touch = not any(draft_tag(n.key) in tags for n in cfg.networks)
    if first_touch:
        log(f"topic {tid}: creating service comment")
        if not cfg.dry_run:
            dc.create_post(tid, render.render_stats(cfg))

    for net in to_draft:
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
        _set_tag(cfg, dc, tid, tags, draft_tag(net.key))


def check(cfg, dc: Discourse) -> None:
    """Read-only auth diagnostic. Prints no secret values — only presence,
    HTTP statuses, and (if auth works) the server-confirmed username."""
    from urllib.parse import urlsplit

    host = urlsplit(cfg.url)
    log(f"url: {host.scheme}://{host.netloc}")
    log(f"api key set: {bool(cfg.api_key)} (length {len(cfg.api_key)})")
    log(f"api username set: {bool(cfg.api_username)} (length {len(cfg.api_username)})")

    about = dc.probe("/about.json", auth=False)
    log(f"GET /about.json (no auth): HTTP {about['status']}  <- confirms URL + reachability")

    sess = dc.probe("/session/current.json", auth=True)
    log(f"GET /session/current.json (auth): HTTP {sess['status']}")
    if sess["status"] == 200:
        user = (sess["body"].get("current_user") or {}) if isinstance(sess["body"], dict) else {}
        log(f"OK — authenticated as '{user.get('username')}'")
    else:
        log(
            "AUTH FAILED. Checklist: (1) key created under Admin -> API; "
            "(2) key scope is Global (or Granular incl. read topics/tags); "
            "(3) DISCOURSE_API_USERNAME is an EXACT existing username; "
            "(4) for a Single-User key it must match that key's user."
        )


def show(cfg, dc: Discourse, topic_id: int) -> None:
    """Read-only: print raw markdown of every comment in a topic."""
    topic = dc.get_topic(topic_id)
    log(f"topic {topic_id}: {topic.get('title')!r}  tags={sorted(topic.get('tags') or [])}")
    for p in (topic.get("post_stream") or {}).get("posts") or []:
        print(f"\n--- #{p.get('post_number')} by {p.get('username')} (id {p['id']}) ---")
        print(dc.get_post_raw(p["id"]))


def _in_scope(cfg, t: dict) -> bool:
    return cfg.category_id is None or t.get("category_id") == cfg.category_id


def list_scope(cfg, dc: Discourse) -> None:
    """Read-only: show which tagged topics are in scope. No generation, no posting."""
    ts = dc.topics_with_tag(cfg.tag)
    scope = f"category={cfg.category_id}" if cfg.category_id is not None else "any category"
    n_in = sum(1 for t in ts if _in_scope(cfg, t))
    log(f"tag='{cfg.tag}', {scope}: {len(ts)} carry the tag, {n_in} in scope")
    for t in ts:
        print(
            f"[{'IN ' if _in_scope(cfg, t) else 'out'}] id={t['id']} "
            f"cat={t.get('category_id')} tags={t.get('tags')} :: {t.get('title')}"
        )


def run_once(cfg, dc: Discourse) -> None:
    for t in dc.topics_with_tag(cfg.tag):
        if not _in_scope(cfg, t):
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
