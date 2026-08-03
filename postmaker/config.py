"""Configuration.

Split by concern:
  - Secrets (Discourse URL / key / username) come from the ENVIRONMENT only.
  - Structure (networks, their limits, prompts, templates, poll cadence, model)
    is declared in a TOML config file — networks/prompts/templates are config.

Env overrides the config file for the handful of operational knobs below.
No state is ever persisted locally: Discourse is the single source of truth.
"""

import os
import tomllib
from dataclasses import dataclass

from .networks import Network


@dataclass(frozen=True)
class Config:
    url: str
    api_key: str
    api_username: str
    tag: str
    category_id: int | None
    poll_interval: int
    claude_bin: str
    claude_model: str
    base_prompt: str
    networks: list[Network]
    dry_run: bool


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _opt_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _load_toml(path: str) -> dict:
    if not os.path.exists(path):
        raise SystemExit(f"Config file not found: {path} (set POSTMAKER_CONFIG)")
    with open(path, "rb") as f:
        return tomllib.load(f)


def _build_networks(raw: list[dict]) -> list[Network]:
    nets = []
    for n in raw:
        limit = n.get("limit")
        nets.append(
            Network(
                key=n["key"],
                label=n.get("label", n["key"].title()),
                emoji=n.get("emoji", "•"),
                limit=(limit if limit else None),  # 0 / missing => unlimited
                split=bool(n.get("split", False)),
                prompt=n["prompt"],
                template=n["template"],
            )
        )
    if not nets:
        raise SystemExit("Config defines no [[networks]]")
    return nets


def load(discourse_required: bool = True) -> Config:
    cfg_path = os.environ.get("POSTMAKER_CONFIG", "postmaker.toml")
    doc = _load_toml(cfg_path)

    def req_env(name: str) -> str:
        v = os.environ.get(name)
        if not v:
            raise SystemExit(f"Missing required env var: {name}")
        return v

    if discourse_required:
        url = req_env("DISCOURSE_URL").rstrip("/")
        api_key = req_env("DISCOURSE_API_KEY")
        api_username = req_env("DISCOURSE_API_USERNAME")
    else:
        url = (os.environ.get("DISCOURSE_URL") or "").rstrip("/")
        api_key = os.environ.get("DISCOURSE_API_KEY") or ""
        api_username = os.environ.get("DISCOURSE_API_USERNAME") or ""

    return Config(
        url=url,
        api_key=api_key,
        api_username=api_username,
        tag=os.environ.get("POSTMAKER_TAG", doc.get("tag", "public")),
        category_id=_opt_int(
            os.environ.get("POSTMAKER_CATEGORY_ID", doc.get("category"))
        ),
        poll_interval=int(
            os.environ.get("POSTMAKER_POLL_INTERVAL", doc.get("poll_interval", 60))
        ),
        claude_bin=os.environ.get("POSTMAKER_CLAUDE_BIN", doc.get("claude_bin", "claude")),
        claude_model=os.environ.get(
            "POSTMAKER_CLAUDE_MODEL", doc.get("claude_model", "claude-opus-4-8")
        ),
        base_prompt=doc.get("base_prompt", "prompts/base.md"),
        networks=_build_networks(doc.get("networks", [])),
        dry_run=_flag("POSTMAKER_DRY_RUN"),
    )
