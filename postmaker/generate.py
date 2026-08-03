"""Text generation via the Claude Code CLI (`claude -p`). No API key needed —
it reuses the already-authenticated CLI. Each network drives its own system
prompt from prompts/<key>.md."""

import os
import re
import subprocess

from .networks import Network


class GenError(RuntimeError):
    pass


def generate(cfg, network: Network, title: str, body: str) -> list[str]:
    """Return the list of post parts for `network` (1 = single post, >1 = thread)."""
    prompt_path = network.prompt
    if not os.path.exists(prompt_path):
        raise GenError(f"missing prompt file: {prompt_path}")

    note = f"Title: {title}\n\n{body}".strip()
    cmd = [
        cfg.claude_bin,
        "-p",
        "--model",
        cfg.claude_model,
        "--append-system-prompt-file",
        prompt_path,
    ]
    proc = subprocess.run(cmd, input=note, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GenError(f"claude failed for {network.key}: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    if not out:
        raise GenError(f"claude returned empty output for {network.key}")
    return _to_parts(network, out)


_COUNTER_RESERVE = 8  # chars kept free for a "12/34 " counter prefix


def _to_parts(network: Network, out: str) -> list[str]:
    if not network.split:
        return [out]

    limit = network.limit
    blocks = [s.strip() for s in _split_on_sep(out) if s.strip()]

    # Fit each author-intended block, reserving room for a counter in case we
    # end up with a thread.
    reserved: list[str] = []
    for b in blocks:
        reserved.extend(_fit(b, limit - _COUNTER_RESERVE) if limit else [b])

    if len(reserved) <= 1:
        # single post: no counter needed, use the full limit
        return _fit(blocks[0], limit) if (blocks and limit) else blocks

    n = len(reserved)
    return [f"{i}/{n} {p}" for i, p in enumerate(reserved, 1)]


def _split_on_sep(text: str) -> list[str]:
    """Split on lines containing exactly `---` (the thread separator)."""
    out, buf = [], []
    for line in text.splitlines():
        if line.strip() == "---":
            out.append("\n".join(buf))
            buf = []
        else:
            buf.append(line)
    out.append("\n".join(buf))
    return out


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _fit(text: str, limit: int) -> list[str]:
    """Pack text into <=limit chunks on sentence boundaries; word-wrap only a
    single sentence that is itself longer than the limit."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for s in _sentences(text):
        candidate = f"{cur} {s}".strip()
        if len(candidate) <= limit:
            cur = candidate
            continue
        if cur:
            chunks.append(cur)
            cur = ""
        if len(s) <= limit:
            cur = s
        else:
            wrapped = _hard_wrap(s, limit)
            chunks.extend(wrapped[:-1])
            cur = wrapped[-1]
    if cur:
        chunks.append(cur)
    return chunks


def _hard_wrap(text: str, limit: int) -> list[str]:
    """Last-resort word wrap for a single over-limit sentence."""
    chunks, cur = [], ""
    for word in text.split():
        candidate = f"{cur} {word}".strip()
        if len(candidate) <= limit:
            cur = candidate
        else:
            if cur:
                chunks.append(cur)
            cur = word[:limit]
    if cur:
        chunks.append(cur)
    return chunks
