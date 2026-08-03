"""Render draft/service comments from per-network templates.

A template is a Markdown file that must contain the hidden idempotency marker
and a `{{PARTS}}` placeholder where the rendered post(s) go. Optional
placeholders: `{{TITLE}}`, `{{COUNT}}`."""

from .networks import Network


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _fmt_part(text: str, limit: int | None) -> str:
    quoted = "\n".join(("> " + ln) if ln.strip() else ">" for ln in text.splitlines())
    meta = f"`{len(text)}" + (f"/{limit}" if limit else "") + " chars`"
    return f"{quoted}\n\n{meta}"


def _render_parts(parts: list[str], limit: int | None) -> str:
    return "\n\n".join(_fmt_part(p, limit) for p in parts)


def render_draft(network: Network, title: str, parts: list[str]) -> str:
    tpl = _read(network.template)
    return (
        tpl.replace("{{PARTS}}", _render_parts(parts, network.limit))
        .replace("{{TITLE}}", title)
        .replace("{{COUNT}}", str(len(parts)))
        .rstrip()
        + "\n"
    )


def render_stats(cfg) -> str:
    return _read(cfg.stats_template).rstrip() + "\n"
