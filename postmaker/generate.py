"""Text generation via the Claude Code CLI, file-based, one session for all
networks.

For a topic we create an isolated temp dir with the note as `note.md` and ask
`claude -p` (once) to WRITE each network's posts as plain-text files under
`out/<network>/NN.txt`. Doing every network in a single session keeps the
English rendering consistent across them (no divergent translations).

We read the files back verbatim — nothing depends on parsing stdout, so model
chatter can't leak into a post and a thread's length is just its file count.
The LLM owns splitting and link placement; the code only VERIFIES each post is
within the platform limit and, on a miss, re-runs with feedback. It never edits
the text itself."""

import glob
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

MAX_ATTEMPTS = 3

_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass
class Post:
    text: str
    images: list[str] = field(default_factory=list)


class GenError(RuntimeError):
    pass


def generate_all(cfg, title: str, body: str, networks: list) -> dict[str, list[Post]]:
    """Generate every network in `networks` in one session.

    Returns {network_key: [Post, ...]}. Raises GenError if, after MAX_ATTEMPTS,
    a network is missing output or still over its limit — better to skip than
    post something broken."""
    networks = list(networks)
    if not networks:
        return {}
    for n in networks:
        if not os.path.exists(n.prompt):
            raise GenError(f"missing prompt file: {n.prompt}")

    image_order = list(dict.fromkeys(_IMG_RE.findall(body)))  # note order, deduped
    valid_images = set(image_order)

    work = tempfile.mkdtemp(prefix="postmaker-")
    try:
        _write(os.path.join(work, "note.md"), f"# {title}\n\n{body}".strip() + "\n")
        for n in networks:
            os.makedirs(os.path.join(work, "out", n.key), exist_ok=True)

        extra = ""
        problem = ""
        for _ in range(MAX_ATTEMPTS):
            for n in networks:
                _clear(os.path.join(work, "out", n.key))
            self_prompt = _build_instruction(cfg, networks, bool(valid_images)) + extra
            proc = subprocess.run(
                [
                    cfg.claude_bin,
                    "-p",
                    self_prompt,
                    "--model",
                    cfg.claude_model,
                    "--permission-mode",
                    "acceptEdits",
                ],
                cwd=work,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise GenError(f"claude failed: {proc.stderr.strip()[:500]}")

            results = {
                n.key: _read_parts(os.path.join(work, "out", n.key), valid_images)
                for n in networks
            }
            # Safety net: never drop the note's images. If the model placed none
            # for a network, attach them all to that network's first post.
            if image_order:
                for n in networks:
                    parts = results[n.key]
                    if parts and not any(p.images for p in parts):
                        parts[0].images = list(image_order)
            missing = [n.key for n in networks if not results[n.key]]
            if missing:
                problem = f"no output written for: {', '.join(missing)}"
                extra = "\n\n" + f"You wrote no file for: {', '.join(missing)}. " + (
                    "Write out/<network>/01.txt for each of them."
                )
                continue

            over = {n.key: _over_limit(n, results[n.key]) for n in networks}
            over = {k: v for k, v in over.items() if v}
            if not over:
                return results
            problem = f"over limit: {over}"
            extra = "\n\n" + _feedback(networks, over)

        raise GenError(f"generation failed after {MAX_ATTEMPTS} attempts ({problem})")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def generate(cfg, network, title: str, body: str) -> list[Post]:
    """Single-network convenience wrapper (used by the `gen` CLI command)."""
    return generate_all(cfg, title, body, [network]).get(network.key, [])


def _build_instruction(cfg, networks: list, has_images: bool) -> str:
    base = _read(cfg.base_prompt).strip() if os.path.exists(cfg.base_prompt) else ""
    lines = [
        base,
        "",
        "Write plain-text files (no Markdown, no formatting) exactly as specified "
        "below. Each post's text file contains ONLY that post's exact text — no "
        "headings, no numbering, no commentary. Overwrite any files already present.",
    ]
    if has_images:
        lines.append(
            "note.md contains one or more images written as ![alt](ref). Keep the "
            "image markup OUT of the .txt files. Every image in the note MUST be "
            "placed: for each post that carries image(s), also write "
            "out/<network>/NN.img next to its NN.txt, one image ref per line, "
            "copied EXACTLY from note.md. Put each image with the first post (01) "
            "unless it clearly belongs with a later post. Do not drop any image."
        )
    for n in networks:
        spec = _read(n.prompt).strip()
        lines.append("")
        lines.append(f"## {n.label}  ->  out/{n.key}/")
        if n.limit:
            lines.append(
                f"Each post <= {n.limit} characters. A single post is "
                f"out/{n.key}/01.txt. Split into out/{n.key}/01.txt, 02.txt, … "
                f"(one post per file) only if it cannot fit; do not number the text."
            )
        else:
            lines.append(f"One file out/{n.key}/01.txt. Long-form, no length limit.")
        if spec:
            lines.append(spec)
    return "\n".join(lines)


def _read_parts(out_dir: str, valid_images: set[str]) -> list[Post]:
    files = glob.glob(os.path.join(out_dir, "*.txt"))
    files.sort(key=_natural_key)
    posts = []
    for f in files:
        text = _read(f).strip()
        if not text:
            continue
        img_path = f[: -len(".txt")] + ".img"
        images = []
        if os.path.exists(img_path):
            for line in _read(img_path).splitlines():
                ref = line.strip()
                if ref and ref in valid_images and ref not in images:
                    images.append(ref)  # only refs that really exist in the note
        posts.append(Post(text=text, images=images))
    return posts


def _natural_key(path: str) -> int:
    nums = re.findall(r"\d+", os.path.basename(path))
    return int(nums[0]) if nums else 0


def _over_limit(network, parts: list[Post]) -> list[tuple[int, int]]:
    if not network.limit:
        return []
    return [(i, len(p.text)) for i, p in enumerate(parts, 1) if len(p.text) > network.limit]


def _feedback(networks: list, over: dict) -> str:
    by_key = {n.key: n for n in networks}
    blocks = []
    for key, items in over.items():
        n = by_key[key]
        rows = "; ".join(f"post {i} is {c} chars" for i, c in items)
        blocks.append(f"- {n.label}: {rows} (limit {n.limit})")
    return (
        "Some posts exceeded their limit:\n"
        + "\n".join(blocks)
        + "\nRewrite those so every post fits. Split into more files if needed. "
        "Never split a sentence or a thought across posts."
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
