"""Text generation via the Claude Code CLI (`claude -p`). No API key needed —
it reuses the already-authenticated CLI. Each network drives its own system
prompt from prompts/<key>.md.

The LLM owns splitting a thread — it understands the meaning and won't cut a
thought in half. The code only VERIFIES the result (each post within the
platform limit) and, on a miss, sends it back for another attempt. The code
never cuts text itself."""

import os
import subprocess

from .networks import Network

MAX_ATTEMPTS = 3  # LLM tries to fit the limit; we verify, not cut


class GenError(RuntimeError):
    pass


def generate(cfg, network: Network, title: str, body: str) -> list[str]:
    """Return the post parts for `network` (1 = single post, >1 = thread).

    Raises GenError if the LLM can't fit the limit after MAX_ATTEMPTS — we would
    rather skip the topic than post a badly-cut thread."""
    if not os.path.exists(network.prompt):
        raise GenError(f"missing prompt file: {network.prompt}")

    note = f"Title: {title}\n\n{body}".strip()
    extra = ""
    over: list[tuple[int, int]] = []
    for _ in range(MAX_ATTEMPTS):
        out = _run_claude(cfg, network, note + extra)
        parts = _parse(network, out)
        over = _over_limit(network, parts)
        if not over:
            return parts
        extra = "\n\n" + _feedback(network, over)

    detail = ", ".join(f"post {i}={n}>{network.limit}" for i, n in over)
    raise GenError(
        f"{network.key}: LLM exceeded {network.limit} chars after "
        f"{MAX_ATTEMPTS} attempts ({detail})"
    )


def _run_claude(cfg, network: Network, text: str) -> str:
    cmd = [
        cfg.claude_bin,
        "-p",
        "--model",
        cfg.claude_model,
        "--append-system-prompt-file",
        network.prompt,
    ]
    proc = subprocess.run(cmd, input=text, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GenError(f"claude failed for {network.key}: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    if not out:
        raise GenError(f"claude returned empty output for {network.key}")
    return out


def _parse(network: Network, out: str) -> list[str]:
    """Turn raw LLM output into posts. We only separate on the LLM's own `---`
    thread markers — we never re-cut the text."""
    if not network.split:
        return [out.strip()]
    return [s.strip() for s in _split_on_sep(out) if s.strip()]


def _split_on_sep(text: str) -> list[str]:
    out, buf = [], []
    for line in text.splitlines():
        if line.strip() == "---":
            out.append("\n".join(buf))
            buf = []
        else:
            buf.append(line)
    out.append("\n".join(buf))
    return out


def _over_limit(network: Network, parts: list[str]) -> list[tuple[int, int]]:
    if not network.limit:
        return []
    return [(i, len(p)) for i, p in enumerate(parts, 1) if len(p) > network.limit]


def _feedback(network: Network, over: list[tuple[int, int]]) -> str:
    lines = "\n".join(f"- post {i} is {n} characters" for i, n in over)
    return (
        f"Your previous attempt exceeded the {network.limit}-character limit:\n"
        f"{lines}\n"
        f"Rewrite the whole thing so EVERY post is at most {network.limit} "
        "characters. Split into more posts if needed, separated by a line "
        "containing exactly ---. Never split a sentence or a thought across posts."
    )
