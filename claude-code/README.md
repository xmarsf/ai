# Claude Code Dev Container (Docker)

Run Claude Code inside an isolated Docker container instead of directly on the host. The workspace is bind-mounted, so edits Claude makes appear directly in your local checkout.

Based on the [official Claude Code dev container docs](https://code.claude.com/docs/en/devcontainer). For the editor-based (VS Code / devcontainer.json) variant, see [script-z-ai/README.md](script-z-ai/README.md).

## 1. Build the image

From this directory (`tools/claude-code/`):

```bash
docker build \
  --build-arg UID=$(id -u) --build-arg GID=$(id -g) \
  -t claude-code .
```

The image is based on `node:22-bookworm` and runs as the non-root `node` user, which the base image already assigns uid/gid `1000`. The `UID`/`GID` build args remap that user to match your host account so the bind-mounted workspace is writable — without this, Claude can read your project but cannot write to it. Claude Code is installed via npm into a user-owned prefix (`~/.npm-global`), which is what makes auto-update work.

## 2. Run Claude Code

From your project root:

```bash
PROJECT=$(basename $(pwd))
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-code-config-$PROJECT:/home/node \
  --cap-drop=ALL \
  claude-code claude
```

### What each part does

| Part | Purpose |
| ------ | --------- |
| `PROJECT=$(basename $(pwd))` | Derives a per-project name from the current directory |
| `-v $(pwd):/workspace` | Bind-mounts the project into the container (`WORKDIR` is `/workspace`) |
| `-v claude-code-config-$PROJECT:/home/node` | Named volume for the `node` home — persists auth, settings, history, **and auto-updated Claude Code versions** (`~/.npm-global` lives here) across runs, isolated per project |
| `--cap-drop=ALL` | Drops all Linux capabilities for a hardened, unprivileged container |
| `--rm` | Removes the container on exit (state lives in the volume, not the container) |
| `claude-code` | Image built in step 1 |
| `claude` | Command to run inside the container |

## 3. Sign in

On first run, follow the authentication prompt inside the container:

- **Anthropic**: browser sign-in with your Claude / Anthropic Console account.
- **API providers (e.g. Z.AI)**: skip browser login by passing env vars:

  ```bash
  docker run -it --rm \
    -v $(pwd):/workspace \
    -v claude-code-config-$PROJECT:/home/node \
    -e ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic" \
    -e ANTHROPIC_AUTH_TOKEN="YOUR_API_KEY" \
    --cap-drop=ALL \
    claude-code claude
  ```

Because auth persists in the named volume, subsequent runs skip login.

> **Warning**: The container isolates command execution, but no system is fully immune. With `--dangerously-skip-permissions`, a malicious project can still exfiltrate anything inside the container, including the credentials in `~/.claude`. Only use this setup with trusted repositories. Do not mount host secrets such as `~/.ssh` or cloud credential files into the container.

## 4. Plugins, skills, and memory files

The container starts with an empty Claude config. Nothing from your host `~/.claude` is visible unless you mount it. Split the config by scope rather than mounting the whole directory — some of it does not survive the move.

| Scope | Lives in | How it gets in |
| ------- | ---------- | ---------------- |
| Project memory / skills / agents | repo `CLAUDE.md`, `.claude/` | already there via the `/workspace` bind-mount — nothing to do |
| Personal skills | host `~/.claude/skills` | read-only bind-mount |
| Personal memory | host `~/.claude/CLAUDE.md` and its `@`-imports | read-only bind-mount |
| Plugins (incl. marketplace skills) | dedicated shared named volume | seeded once from inside a container via `claude plugin` |
| Auth, history, state | per-project volume from step 2 | already handled |

Nested mounts are fine: Docker applies them in order of path depth, so a bind-mount at `/home/node/.claude/skills` layers cleanly on top of the named volume at `/home/node`.

### Personal skills and memory

```bash
-v $HOME/.claude/skills:/home/node/.claude/skills:ro \
-v $HOME/.claude/CLAUDE.md:/home/node/.claude/CLAUDE.md:ro
```

Mount each file that `CLAUDE.md` pulls in with `@import` separately — imports are resolved as paths, and an unmounted one silently resolves to nothing.

`:ro` means the container cannot corrupt your host skills; it also means Claude cannot install new skills for itself. Drop `:ro` if you want writes to flow back to the host.

### Plugins (and marketplace skills)

Skills published on a marketplace arrive as plugins, not as loose skill directories. Two pieces of state have to agree for one to load:

- `~/.claude/plugins/installed_plugins.json` — the install record, holding an absolute `installPath`
- `enabledPlugins` in `~/.claude/settings.json` — whether it is switched on

Do **not** bind-mount host `~/.claude/plugins`. Its `installPath` values point under your host home (`/home/xmars/.claude/plugins/...`), which does not exist in the container, where home is `/home/node`. The plugins would be listed but unresolvable. It is also large — a populated plugin directory runs to a gigabyte or more of marketplace clones and caches.

Give plugins their own named volume and populate it from inside a container, so the recorded paths are container-native. The `claude plugin` CLI does this without an interactive session:

```bash
docker volume create claude-plugins
mkdir -p $HOME/.claude-docker && echo '{}' > $HOME/.claude-docker/settings.json

docker run --rm \
  -v claude-plugins:/home/node/.claude/plugins \
  -v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json \
  --cap-drop=ALL \
  claude-code bash -lc '
    claude plugin marketplace add JuliusBrussee/caveman
    claude plugin install -y caveman@caveman
  '
```

`marketplace add` takes a GitHub repo, URL, or path; `install` takes `plugin@marketplace`. `-y` is required whenever stdin is not a TTY. `claude plugin list` and `claude plugin update <plugin>` work the same way later.

Mount `settings.json` **read-write** here (no `:ro`): `plugin install` writes `enabledPlugins` and `extraKnownMarketplaces` into it. Keeping it on the host at `$HOME/.claude-docker/settings.json` means one seeding run serves every project.

Then add both mounts to every project run:

```bash
-v claude-plugins:/home/node/.claude/plugins \
-v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json
```

#### Keeping the volume small

Marketplaces hosted in a monorepo clone the whole repository. Limit the checkout:

```bash
claude plugin marketplace add anthropics/claude-plugins --sparse .claude-plugin plugins
```

#### Approaches that do not work

| Approach | Why not |
| ---------- | --------- |
| Bind-mount host `~/.claude/plugins:ro` | `installPath` records the host home; the paths do not exist under `/home/node` |
| `RUN claude plugin install` in the Dockerfile | A named volume is seeded from the image only the first time it is mounted while empty, so a rebuild never refreshes an existing volume |
| Copy a plugin's `skills/` into `~/.claude/skills/<name>` | The skills load, but the plugin's commands, agents, hooks, and MCP servers do not, and updates become manual |

### settings.json

Do not mount your host `settings.json`. Hook commands in it are absolute host paths (an nvm-managed `node` binary, scripts under `~/.claude/hooks`) and it may invoke host-only tools; none of that resolves inside the container.

Use the container-specific copy from the plugin step instead — `$HOME/.claude-docker/settings.json`, mounted read-write so plugin installs can record themselves:

```bash
-v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json
```

Everything else in it (model, permissions, env) is yours to fill in, as long as it holds no host paths and no host-only tools.

To run your hooks in the container too, also mount `-v $HOME/.claude/hooks:/home/node/.claude/hooks:ro` and rewrite each hook command against container paths — `node` is already on `PATH` in the image, so `node /home/node/.claude/hooks/<script>.js` works.

### Full run command

```bash
PROJECT=$(basename $(pwd))
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-code-config-$PROJECT:/home/node \
  -v claude-plugins:/home/node/.claude/plugins \
  -v $HOME/.claude/skills:/home/node/.claude/skills:ro \
  -v $HOME/.claude/CLAUDE.md:/home/node/.claude/CLAUDE.md:ro \
  -v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json \
  --cap-drop=ALL \
  claude-code claude
```

### Alternative: mirror the host home path

If you would rather reuse the host config wholesale, build the image with the container home set to the same path as your host home (`usermod -d $HOME -m node`). Host `~/.claude` then bind-mounts verbatim and the absolute paths in `installed_plugins.json` and `settings.json` resolve correctly.

The trade-off: the image becomes specific to one host account, and mounting `~/.claude` writable exposes `.credentials.json` and your entire session history to whatever runs in the container — the same risk as the warning above, over a much wider surface.

## 5. Reset project state (optional)

To wipe saved auth, settings, and history for a project, delete its volume:

```bash
docker volume rm claude-code-config-$PROJECT
```
