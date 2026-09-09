# Claude Code Dev Container (Docker)

Run Claude Code in an isolated Docker container. Workspace is bind-mounted, so edits appear directly in your local checkout.

Based on the [official dev container docs](https://code.claude.com/docs/en/devcontainer).

> **Security**: `--dangerously-skip-permissions` lets a malicious project exfiltrate anything in the container, including credentials. Only use with trusted repos. Never mount host secrets (`~/.ssh`, cloud credential files).

## 1. Build

```bash
docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -t claude-code .
```

Base image `node:22-bookworm`, runs as non-root `node`. `UID`/`GID` remap that user to your host account so the bind-mounted workspace is writable. Claude Code installs into `~/.npm-global` (user-owned, so auto-update works).

## 2. Run (with memory + skills)

```bash
PROJECT=$(basename $(pwd))
AI_REPO=$HOME/dev/vdx-vn/ai
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-code-config-$PROJECT:/home/node \
  -v claude-plugins:/home/node/.claude/plugins \
  -v $AI_REPO/skills:/home/node/.claude/skills:ro \
  -v $AI_REPO/claude-code/CLAUDE.md:/home/node/.claude/CLAUDE.md:ro \
  -v $AI_REPO/claude-code/CLAUDE.odoo.md:/home/node/.claude/CLAUDE.odoo.md:ro \
  -v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json \
  --cap-drop=ALL \
  claude-code claude --dangerously-skip-permissions
```

- `claude-code-config-$PROJECT` — named volume, per project: auth, settings, history, npm-global (auto-updated CC versions)
- `claude-plugins` — writable `~/.claude/plugins` (marketplace installs, see §3)
- Skills + memory mounts — repo-local skills and `CLAUDE.md`, which imports `CLAUDE.odoo.md` via `@CLAUDE.odoo.md`; both files are mounted `:ro` at their own names. Swap `CLAUDE.odoo.md` for the guide that fits the project (update the import accordingly), or drop both mounts.
- `--cap-drop=ALL` / `--rm` — hardened, unprivileged, disposable container; state lives in the volumes

First run: browser login prompt inside the container; auth persists in the volume, later runs skip login.

The container starts with empty config — nothing from host `~/.claude` unless mounted. Mount by scope, not the whole directory: `installed_plugins.json` records host-absolute paths that don't exist under `/home/node`. `:ro` means the container can't corrupt host files or self-install skills (drop it to allow writes back). Mount each `@import`ed file separately — imports resolve as paths, an unmounted one silently resolves to nothing.

### Minimal run

```bash
PROJECT=$(basename $(pwd))
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-code-config-$PROJECT:/home/node \
  --cap-drop=ALL \
  claude-code claude
```

### Use host skills/memory instead

```bash
-v $HOME/.claude/skills:/home/node/.claude/skills:ro \
-v $HOME/.claude/CLAUDE.md:/home/node/.claude/CLAUDE.md:ro
```

## 3. Plugins, hooks, alternatives

Recommended marketplaces — auto-installed/updated by `entrypoint.sh` on every container start (needs a writable `~/.claude/plugins`, e.g. the `claude-plugins` volume):

- [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) — official (includes `superpowers`)
- [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — third-party (`caveman`)

Host hooks: `-v $HOME/.claude/hooks:/home/node/.claude/hooks:ro`, and point hook commands at `node /home/node/.claude/hooks/<script>.js` (container `PATH` already has `node`).

**Alternative — mirror host home path**: build with `usermod -d $HOME -m node` so container home == host home; host `~/.claude` then bind-mounts verbatim and absolute paths in `installed_plugins.json`/`settings.json` resolve. Trade-off: image tied to one host account, and a writable `~/.claude` mount exposes `.credentials.json` + full session history to anything running in the container.

## 4. Reset project state

```bash
docker volume rm claude-code-config-$PROJECT
```

Wipes saved auth, settings, history for that project.
