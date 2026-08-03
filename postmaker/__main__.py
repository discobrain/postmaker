"""CLI.

  postmaker run          poll forever, draft new public topics
  postmaker once         a single pass, then exit
  postmaker check        read-only: diagnose Discourse auth (no secrets printed)
  postmaker topics       read-only: list tagged topics and their scope
  postmaker gen <net>    generate <net> from a note on stdin (no Discourse needed)
"""

import sys

from . import config, loop
from .discourse import Discourse
from .generate import generate


def _cmd_gen(argv: list[str]) -> int:
    if len(argv) < 1:
        print("usage: postmaker gen <network>  (note on stdin)", file=sys.stderr)
        return 2
    cfg = config.load(discourse_required=False)
    net = next((n for n in cfg.networks if n.key == argv[0]), None)
    if net is None:
        print(f"unknown network: {argv[0]}", file=sys.stderr)
        return 2
    note = sys.stdin.read()
    parts = generate(cfg, net, "Untitled", note)
    for i, p in enumerate(parts, 1):
        print(f"--- {net.key} part {i}/{len(parts)} ({len(p)} chars) ---")
        print(p)
    return 0


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "run"
    rest = argv[1:]
    if cmd == "run":
        loop.run(config.load())
        return 0
    if cmd == "once":
        cfg = config.load()
        loop.run_once(cfg, Discourse(cfg.url, cfg.api_key, cfg.api_username))
        return 0
    if cmd == "check":
        cfg = config.load()
        loop.check(cfg, Discourse(cfg.url, cfg.api_key, cfg.api_username))
        return 0
    if cmd == "topics":
        cfg = config.load()
        loop.list_scope(cfg, Discourse(cfg.url, cfg.api_key, cfg.api_username))
        return 0
    if cmd == "gen":
        return _cmd_gen(rest)
    print(__doc__)
    return 0 if cmd in ("-h", "--help", "help") else 2


if __name__ == "__main__":
    raise SystemExit(main())
