"""Render draft/service comments from per-network templates.

A template is a Markdown file for how the Discourse comment LOOKS (presentation
only — nothing functional depends on its text). Placeholders:
  {{PARTS}}    -> the post(s), each in a ```md fence (verbatim, copy-pasteable)
  {{BACKLOG}}  -> the network's backlog topic URL (its line is dropped if unset)
  {{TITLE}}    -> the source note title
"""

from .networks import Network


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _fence(text: str, limit: int | None) -> str:
    block = f"```md\n{text}\n```"
    if limit:
        block += f"\n`{len(text)}/{limit}`"
    return block


def _render_parts(parts: list[str], limit: int | None) -> str:
    return "\n\n".join(_fence(p, limit) for p in parts)


def _apply_backlog(text: str, backlog: str | None) -> str:
    if backlog:
        return text.replace("{{BACKLOG}}", backlog)
    # no backlog configured -> drop the whole line carrying the placeholder
    return "\n".join(ln for ln in text.splitlines() if "{{BACKLOG}}" not in ln)


def render_draft(network: Network, title: str, parts: list[str]) -> str:
    tpl = _read(network.template)
    body = tpl.replace("{{PARTS}}", _render_parts(parts, network.limit))
    body = _apply_backlog(body, network.backlog)
    body = body.replace("{{TITLE}}", title)
    return body.rstrip() + "\n"


def render_stats(cfg) -> str:
    return _read(cfg.stats_template).rstrip() + "\n"
