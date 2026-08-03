"""Network shape. The actual list of networks — with their limits, prompt files
and comment templates — is declared in the config file (postmaker.toml), not here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Network:
    key: str            # also the Discourse tag set when this network's draft is ready
    label: str
    emoji: str
    limit: int | None   # per-post character limit; None = unlimited
    split: bool         # allow splitting into a numbered thread on overflow
    prompt: str         # path to the translation/adaptation system prompt
    template: str       # path to the Discourse comment template


STATS_MARKER = "<!-- postmaker:stats -->"


def draft_marker(key: str) -> str:
    return f"<!-- postmaker:draft:{key} -->"
