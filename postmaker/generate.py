"""Text generation via the Claude Code CLI (`claude -p`). No API key needed —
it reuses the already-authenticated CLI. Each network drives its own system
prompt from prompts/<key>.md."""

import os
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


def _to_parts(network: Network, out: str) -> list[str]:
    if network.split:
        parts = [p for p in (s.strip() for s in _split_on_sep(out)) if p]
    else:
        parts = [out]
    if network.split and len(parts) > 1:
        n = len(parts)
        parts = [f"{i}/{n} {p}" for i, p in enumerate(parts, 1)]
    if network.limit:
        parts = _enforce_limit(parts, network.limit)
    return parts


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


def _enforce_limit(parts: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for p in parts:
        if len(p) <= limit:
            result.append(p)
        else:
            result.extend(_hard_wrap(p, limit))
    return result


def _hard_wrap(text: str, limit: int) -> list[str]:
    """Deterministic fallback: word-wrap an over-limit part into <=limit chunks."""
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
