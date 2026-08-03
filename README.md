# postmaker

Drafts your Discourse notes into ready-to-review posts for **site**, **Threads**
and **Bluesky**, straight back into the Discourse topic. You then review, edit
and approve by ❤️-liking the draft — a separate *publisher* tool picks approved
drafts up and posts them.

This repo is the **drafter** only.

## How it works

An infinite poll loop, with **Discourse as the only source of truth** — nothing
is stored locally:

1. Find topics tagged `public` (optionally restricted to a category via
   `category` in `postmaker.toml`) that don't yet carry all network tags.
2. For each, right after the first post, ensure a **service comment** exists
   (reserved for future stats).
3. For each network without its tag yet: generate the post with `claude -p`
   using that network's prompt, post it as a comment from its template, then set
   the network's tag (`site` / `threads` / `bluesky`) to mark the draft ready.

State is derived every pass:

- network tag present → that draft is ready (set by us when done)
- hidden comment marker (`<!-- postmaker:draft:threads -->` etc.) → dedup /
  crash-recovery between posting the comment and setting the tag

Overflowing posts are split into a numbered thread (Threads ≤ 500, Bluesky ≤ 300
chars). The `site` draft is long-form, unlimited.

## Configure

- **Secrets** → environment (`.env`): `DISCOURSE_URL`, `DISCOURSE_API_KEY`,
  `DISCOURSE_API_USERNAME`. See `.env.example`.
- **Structure** → `postmaker.toml`: the networks, their limits, and each one's
  prompt (`prompts/<net>.md`) and comment template (`templates/<net>.md`).

Networks, prompts and templates are all config — edit them freely.

## Run

```sh
cp .env.example .env    # fill in Discourse secrets (plain KEY=value)
direnv allow            # loads the flake dev shell + .env (see .envrc)
# no direnv? -> `nix develop` and `set -a; source .env; set +a`

# smoke-test generation only (no Discourse needed):
printf 'Title: Test\n\nMy note about X' | python -m postmaker gen threads

# one pass / forever:
POSTMAKER_DRY_RUN=1 python -m postmaker once   # generate + print, don't post
python -m postmaker run                         # poll forever
```

Or via the flake app:

```sh
nix run . -- once
```

Requirements: the `claude` CLI on PATH, already authenticated. Generation uses
`claude -p --model claude-opus-4-8` with the per-network prompt — no separate
API key.
