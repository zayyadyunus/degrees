---
name: deploy
description: Deploy Degrees to Fly.io safely — tests, playtest, single-machine deploy, live health and smoke check, with rollback steps.
disable-model-invocation: true
---

# Deploy to Fly.io

The app keeps games in process memory, so it must run as **exactly one
machine**. Every step below protects that or verifies the release.

## 0. Preconditions

- `fly auth whoami` succeeds. If not, ask the user to run `! fly auth login`
  (interactive; you can't do it for them).
- `git status --short` is clean — deploy committed code only, so the release
  maps to a commit. If dirty, stop and ask.
- The app exists: `fly status`. First deploy only: `fly apps create <name>`
  with the name in `fly.toml` (pick another if taken, and update `fly.toml`).

## 1. Verify locally

```bash
cd backend && .venv/bin/python -m pytest -q && cd ..
scripts/playtest.sh
```

Stop on any failure. Also run `cd backend && .venv/bin/python
scripts/preview_dailies.py --days 3` and show the user today's and the next
two dailies: they go live with this deploy.

## 2. Deploy

```bash
fly deploy --ha=false
```

`--ha=false` is mandatory: without it Fly creates two machines and games
start 404ing on whichever machine didn't create them. The image builds on
Fly's remote builder from the repo `Dockerfile`.

Then confirm exactly one machine:

```bash
fly machines list
```

If there are more than one: `fly scale count 1 --yes`.

## 3. Verify live

```bash
curl -s https://<app>.fly.dev/health      # synthetic_embeddings must be false
backend/.venv/bin/python backend/scripts/smoke_api.py https://<app>.fly.dev
```

Open the URL for the user (or give it) so they can play the daily once.

## Rollback

```bash
fly releases                     # find the last good version's image
fly deploy --image <image-ref> --ha=false
```

A deploy or rollback restarts the machine: in-progress games are lost.
Dailies recover (same puzzle, fresh game); practice games don't.

## Report

Release version, commit hash, live URL, `/health` output, smoke result, and
today's daily.
