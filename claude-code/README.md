# Claude Code Dev Container (Docker)

Run Claude Code in an isolated Docker container. Workspace is bind-mounted, so edits appear directly in your local checkout.

Based on the [official dev container docs](https://code.claude.com/docs/en/devcontainer).

> **Security**: `--dangerously-skip-permissions` lets a malicious project exfiltrate anything in the container, including credentials. Only use with trusted repos. Never mount host secrets (`~/.ssh`, cloud credential files).

## 1. Build

```bash
docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -t claude-code .
```

Base image `node:22-bookworm`, runs as non-root `node`. `UID`/`GID` remap that user to your host account so the bind-mounted workspace is writable. Claude Code installs into `~/.npm-global` (user-owned, so auto-update works).

## 2. Run

```bash
PROJECT=$(basename $(pwd))
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-code-config-$PROJECT:/home/node \
  --cap-drop=ALL \
  claude-code claude
```

- `claude-code-config-$PROJECT` — named volume, per project: auth, settings, history, npm-global (auto-updated CC versions)
- `--cap-drop=ALL` — hardened, unprivileged container
- `--rm` — container is disposable, state lives in the volume

## 3. Sign in

First run: browser login prompt inside the container. Auth persists in the volume — later runs skip login.

## 4. Plugins, skills, memory (optional)

Container starts with empty config — nothing from host `~/.claude` unless mounted. Mount by scope, not the whole directory (some of it breaks across the move: `installed_plugins.json` records host-absolute paths that don't exist under `/home/node`).

**Recommended: repo-local config** — skills and memory come from this repo, portable, no host dependency:

```bash
PROJECT=$(basename $(pwd))
AI_REPO=$HOME/dev/vdx-vn/ai
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-code-config-$PROJECT:/home/node \
  -v claude-plugins:/home/node/.claude/plugins \
  -v $AI_REPO/skills:/home/node/.claude/skills:ro \
  -v $AI_REPO/claude-code/CLAUDE.odoo.md:/home/node/.claude/CLAUDE.md:ro \
  -v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json \
  --cap-drop=ALL \
  claude-code claude
```

Swap `CLAUDE.odoo.md` for whatever memory file fits the project, or drop that mount entirely.

### Use host skills/memory instead

```bash
-v $HOME/.claude/skills:/home/node/.claude/skills:ro \
-v $HOME/.claude/CLAUDE.md:/home/node/.claude/CLAUDE.md:ro
```

`:ro` = container can't corrupt host files, and can't self-install skills. Drop it to allow writes back. Mount each `@import`ed file separately — imports resolve as paths, an unmounted one silently resolves to nothing.

### Plugins (marketplace skills)

Never bind-mount host `~/.claude/plugins` — its `installPath` values point at your host home, which doesn't exist in the container (also often 1GB+). Instead, give plugins their own named volume and seed it from inside a container:

```bash
docker volume create claude-plugins
mkdir -p $HOME/.claude-docker && [ -f $HOME/.claude-docker/settings.json ] || echo '{}' > $HOME/.claude-docker/settings.json

docker run --rm \
  -v claude-plugins:/home/node/.claude/plugins \
  -v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json \
  --cap-drop=ALL \
  claude-code bash -lc '
    claude plugin marketplace add JuliusBrussee/caveman
    claude plugin install -y caveman@caveman
    claude plugin install -y superpowers@claude-plugins-official
  '
```

Superpowers is on the official marketplace already known to `claude` — no `marketplace add` needed, only caveman's third-party one. Safe to re-run — installed plugins are skipped. Order vs. step 2 doesn't matter, volume just needs seeding before use.

Monorepo marketplace clones the whole repo — sparse-checkout to keep it small:

```bash
claude plugin marketplace add anthropics/claude-plugins --sparse .claude-plugin plugins
```

`settings.json` must be mounted **read-write** (no `:ro`) for plugin installs — `plugin install` writes `enabledPlugins`/`extraKnownMarketplaces` into it. Keep it at `$HOME/.claude-docker/settings.json` (container-specific — host `settings.json` has host-only hook paths that won't resolve in the container). Optional if you never install marketplace plugins.

To run host hooks too: `-v $HOME/.claude/hooks:/home/node/.claude/hooks:ro`, and point hook commands at `node /home/node/.claude/hooks/<script>.js` (container `PATH` already has `node`).

### Alternative: mirror host home path

Build with `usermod -d $HOME -m node` so container home == host home — then host `~/.claude` bind-mounts verbatim and absolute paths in `installed_plugins.json`/`settings.json` resolve. Trade-off: image tied to one host account, and a writable `~/.claude` mount exposes `.credentials.json` + full session history to anything running in the container.

## 5. Reset project state

```bash
docker volume rm claude-code-config-$PROJECT
```

Wipes saved auth, settings, history for that project.
