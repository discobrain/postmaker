"""Text generation via the Claude Code CLI, file-based.

For each network we create an isolated temp dir containing just `note.md`, then
ask `claude -p` to WRITE the result as numbered post files `out/01.md`,
`out/02.md`, … — one file per post in the thread. We read those files back
verbatim. Nothing depends on parsing stdout, so stray model chatter can't leak
into a post, and the thread length is simply the number of files.

The LLM owns splitting and link/image placement (it understands the content).
The code only VERIFIES each post is within the platform limit and, on a miss,
re-runs with feedback. The code never edits the text itself."""

import glob
import os
import re
import shutil
import subprocess
import tempfile

from .networks import Network

MAX_ATTEMPTS = 3

_INSTRUCTION = (
    "Read note.md in the current directory. Produce the {label} version of it, "
    "following the system instructions. Write each post as its own PLAIN-TEXT "
    "file under out/: out/01.txt, out/02.txt, … in order. A single post means "
    "only out/01.txt. Each file must contain ONLY that post's exact text as plain "
    "text — no Markdown, no formatting, no headings, no numbering, no commentary, "
    "nothing but what a reader should see. Overwrite any files already in out/."
)


class GenError(RuntimeError):
    pass


def generate(cfg, network: Network, title: str, body: str) -> list[str]:
    """Return the post parts for `network` (1 = single post, >1 = thread).

    Raises GenError if the LLM can't fit the limit after MAX_ATTEMPTS — we would
    rather skip the topic than post a badly-cut thread."""
    if not os.path.exists(network.prompt):
        raise GenError(f"missing prompt file: {network.prompt}")

    work = tempfile.mkdtemp(prefix="postmaker-")
    try:
        _write(os.path.join(work, "note.md"), f"# {title}\n\n{body}".strip() + "\n")
        out_dir = os.path.join(work, "out")
        os.makedirs(out_dir, exist_ok=True)

        extra = ""
        over: list[tuple[int, int]] = []
        for _ in range(MAX_ATTEMPTS):
            _clear(out_dir)
            self_prompt = _INSTRUCTION.format(label=network.label) + extra
            proc = subprocess.run(
                [
                    cfg.claude_bin,
                    "-p",
                    self_prompt,
                    "--model",
                    cfg.claude_model,
                    "--append-system-prompt-file",
                    os.path.abspath(network.prompt),
                    "--permission-mode",
                    "acceptEdits",
                ],
                cwd=work,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise GenError(
                    f"claude failed for {network.key}: {proc.stderr.strip()[:500]}"
                )
            parts = _read_parts(out_dir)
            if not parts:
                raise GenError(
                    f"{network.key}: no out/*.md produced "
                    f"(stdout: {proc.stdout.strip()[:200]!r})"
                )
            over = _over_limit(network, parts)
            if not over:
                return parts
            extra = "\n\n" + _feedback(network, over)

        detail = ", ".join(f"post {i}={n}>{network.limit}" for i, n in over)
        raise GenError(
            f"{network.key}: LLM exceeded {network.limit} chars after "
            f"{MAX_ATTEMPTS} attempts ({detail})"
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _read_parts(out_dir: str) -> list[str]:
    files = glob.glob(os.path.join(out_dir, "*.txt"))
    files.sort(key=_natural_key)
    return [t for t in (_read(f).strip() for f in files) if t]


def _natural_key(path: str) -> int:
    nums = re.findall(r"\d+", os.path.basename(path))
    return int(nums[0]) if nums else 0


def _over_limit(network: Network, parts: list[str]) -> list[tuple[int, int]]:
    if not network.limit:
        return []
    return [(i, len(p)) for i, p in enumerate(parts, 1) if len(p) > network.limit]


def _feedback(network: Network, over: list[tuple[int, int]]) -> str:
    lines = "\n".join(f"- post {i} is {n} characters" for i, n in over)
    return (
        f"Your previous attempt exceeded the {network.limit}-character limit:\n"
        f"{lines}\n"
        f"Rewrite so EVERY post is at most {network.limit} characters. Split into "
        "more posts if needed. Never split a sentence or a thought across posts."
    )


def _clear(out_dir: str) -> None:
    for f in glob.glob(os.path.join(out_dir, "*.txt")):
        os.remove(f)


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()
