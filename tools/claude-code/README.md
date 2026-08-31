# Claude Code Dev Container (Docker)

Run Claude Code inside an isolated Docker container instead of directly on the host. The workspace is bind-mounted, so edits Claude makes appear directly in your local checkout.

Based on the [official Claude Code dev container docs](https://code.claude.com/docs/en/devcontainer). For the editor-based (VS Code / devcontainer.json) variant, see [script-z-ai/README.md](script-z-ai/README.md).

## 1. Build the image

From this directory (`tools/claude-code/`):

```bash
docker build -t my-claude-dev .
```

The image is based on `node:22-bookworm`, installs Claude Code via npm into a `dev`-owned prefix (`~/.npm-global`, so auto-update works), and runs as the non-root `dev` user.

## 2. Run Claude Code

From your project root:

```bash
PROJECT=$(basename $(pwd))
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-code-config-$PROJECT:/home/dev \
  --cap-drop=ALL \
  my-claude-dev claude
```

### What each part does

| Part | Purpose |
|------|---------|
| `PROJECT=$(basename $(pwd))` | Derives a per-project name from the current directory |
| `-v $(pwd):/workspace` | Bind-mounts the project into the container (`WORKDIR` is `/workspace`) |
| `-v claude-code-config-$PROJECT:/home/dev` | Named volume for the `dev` home — persists auth, settings, history, **and auto-updated Claude Code versions** (`~/.npm-global` lives here) across runs, isolated per project |
| `--cap-drop=ALL` | Drops all Linux capabilities for a hardened, unprivileged container |
| `--rm` | Removes the container on exit (state lives in the volume, not the container) |
| `my-claude-dev` | Image built in step 1 |
| `claude` | Command to run inside the container |

## 3. Sign in

On first run, follow the authentication prompt inside the container:

- **Anthropic**: browser sign-in with your Claude / Anthropic Console account.
- **API providers (e.g. Z.AI)**: skip browser login by passing env vars:

  ```bash
  docker run -it --rm \
    -v $(pwd):/workspace \
    -v claude-code-config-$PROJECT:/home/dev \
    -e ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic" \
    -e ANTHROPIC_AUTH_TOKEN="YOUR_API_KEY" \
    --cap-drop=ALL \
    my-claude-dev claude
  ```

Because auth persists in the named volume, subsequent runs skip login.

> **Warning**: The container isolates command execution, but no system is fully immune. With `--dangerously-skip-permissions`, a malicious project can still exfiltrate anything inside the container, including the credentials in `~/.claude`. Only use this setup with trusted repositories. Do not mount host secrets such as `~/.ssh` or cloud credential files into the container.

## 4. Reset project state (optional)

To wipe saved auth, settings, and history for a project, delete its volume:

```bash
docker volume rm claude-code-config-$PROJECT
```
