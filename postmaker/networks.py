"""Network shape. The actual list of networks — with their limits, prompt files
and comment templates — is declared in the config file (postmaker.toml), not here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Network:
    key: str            # also the Discourse tag set when this network's draft is ready
    label: str
    emoji: str
    limit: int | None   # per-post character limit; None = unlimited
    split: bool         # allow splitting into a thread on overflow
    prompt: str         # path to the translation/adaptation system prompt
    template: str       # path to the Discourse comment template
    backlog: str | None # URL of this network's backlog topic (optional)


def draft_tag(key: str) -> str:
    """Topic tag meaning: this network's draft is ready (set by the drafter)."""
    return f"{key}-draft"


def published_tag(key: str) -> str:
    """Topic tag meaning: this network is published (set by the publisher)."""
    return f"{key}-published"
