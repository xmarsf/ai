# odoo-deploy setup

One-time setup for driving GitLab MR pipelines to green through a
webhook-delivered result. Each section below is what a `check-setup`
failure's `fix` field points to.

## 1. Prerequisites

- Owner or Maintainer access (GitLab access level ≥ 40) on the **upstream**
  project — the one the MR pipeline actually runs in, even for a fork MR
  (see the design spec's "Environment facts" for why).
- Docker enabled at boot (`systemctl is-enabled docker` → `enabled`) and
  your user in the `docker` group (`groups | grep docker`) — the compose
  stack must survive a reboot without anyone logging in to start it.
- `uvx` on `PATH` (part of [uv](https://docs.astral.sh/uv/)) — used by
  `gitlab_ci.py lint` to run a pinned `ruff` version without installing it
  into any project venv.
- Access to the `vdx.vn` Cloudflare Zero Trust account, with permission to
  create tunnels and public hostnames in that zone.

## 2. Cloudflare tunnel

1. In the Cloudflare Zero Trust dashboard, create a **remotely managed**
   tunnel (not a quick tunnel — its URL changes on every run, which would
   mean re-creating the GitLab hook every time).
2. Add a public hostname, e.g. `odoo-deploy.vdx.vn`, routing to
   `http://listener:8080` (the `listener` service name from
   `docker/compose.yml` — Docker's internal DNS resolves it; this is not
   `localhost`).
3. Copy the tunnel token from the dashboard.
4. In this skill's directory:

   ```bash
   cp docker/.env.example docker/.env
   chmod 600 docker/.env
   ```

   Edit `docker/.env` and set:

   ```
   TUNNEL_TOKEN=<the token from step 3>
   HOOK_HOSTNAME=odoo-deploy.vdx.vn
   ```

   Leave every other key in `docker/.env` blank — `gitlab_ci.py setup`
   (section 5) fills them in.

## 3. Project config

From the Odoo workspace root (where `config/project.json` lives):

```bash
odoo setup --force --setup-telegram
```

This (re)writes `config/project.json`, adding `git_root`/`gitlab_url`
(discovered from the addons checkout's git remotes) and, via
`--setup-telegram`, `telegram_channel`/`telegram_token` (prompted
interactively, then verified against the real Telegram Bot API). Run
without `--setup-telegram` only if those two fields are already set some
other way — `check-setup` check `g` needs both.

## 4. GitLab token

Nothing to do if `git push` to `origin` already works from this machine —
the same credential (from `~/.gitlab` or your normal git credential helper,
e.g. `glab`'s) is reused for the GitLab REST API calls.

Otherwise, create a Personal Access Token on `gitlab.vdx.vn` with the `api`
scope, then add it to `~/.gitlab`:

```ini
[gitlab]
https://gitlab.vdx.vn/ = <your-token>
```

## 5. Run setup

From the Odoo workspace root (or any directory under it):

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py setup
```

This fills in the remaining `docker/.env` keys, brings up the `cloudflared`
+ `listener` containers (`restart: unless-stopped` — they survive a reboot
once Docker itself is enabled at boot), and creates/updates a single
pipeline-events-only hook on the upstream project. It ends by running
`check-setup` and embedding the result under `check` — expect
`check.ok: true`. If it isn't, see Troubleshooting below for the specific
failing check id.

## 6. Troubleshooting

Each row is a `check-setup` check id.

| id | Checks | If it fails |
|---|---|---|
| a | `config/project.json` has `git_root`/`gitlab_url`; `origin`+`upstream` git remotes exist; `upstream`'s host matches `gitlab_url` | Re-run section 3; confirm the addons checkout actually has both remotes (`git remote -v`) |
| b | A GitLab token resolves and `GET /user` succeeds | Section 4 |
| c | `docker/.env` has all six keys | Re-run section 2, then section 5 (`setup` fills the automatic ones) |
| d | `docker compose ps` shows both `cloudflared` and `listener` running | Re-run section 5 (`gitlab_ci.py setup` brings the stack up); if it's crash-looping instead, `docker compose -f $SKILL_DIR/docker/compose.yml logs` to see why — usually a bad `TUNNEL_TOKEN` or a `WEBHOOK_SECRET`/`FORK_PROJECT_ID` missing from `.env` |
| e | The upstream project has exactly one hook at `https://$HOOK_HOSTNAME/hook`, `pipeline_events: true`, `alert_status: executable` | Re-run section 5 (`setup` creates/updates it); a non-`executable` `alert_status` means GitLab is failing to deliver — check `d` and the Cloudflare dashboard first |
| f | `uvx` on `PATH` | Section 1 |
| g | `telegram_channel`/`telegram_token` in `config/project.json`; Telegram `getMe` succeeds | Re-run section 3 with `--setup-telegram` |
| h | A real test delivery (`POST .../hooks/:id/test/pipeline_events`) reaches the listener within 15s | Confirm the Cloudflare public hostname is routed and the tunnel container (`d`) is actually connected — check the Cloudflare Zero Trust dashboard's tunnel status |

## Never

The agent driving this skill never merges, approves, or enables auto-merge
on any MR — see `SKILL.md` "No-merge rule". This setup only grants it push
and MR-open access; merging stays a human decision.
