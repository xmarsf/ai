# Run Claude Code Inside a Dev Container

Step-by-step guide to set up a development container (dev container) so Claude Code runs inside an isolated, reproducible environment instead of directly on your host.

Reference: [official Claude Code dev container docs](https://code.claude.com/docs/en/devcontainer).

## How dev containers work with your editor

A dev container is a Docker container defined by a `devcontainer.json` file (see [containers.dev](https://containers.dev/)). An editor with Dev Containers support — VS Code, Cursor, JetBrains IDEs, GitHub Codespaces — connects to that container:

- You browse and edit files in your editor as usual.
- The integrated terminal, language servers, build tools, and **Claude Code** all run *inside* the container.
- Your repository is bind-mounted into the container as the workspace, so edits Claude makes appear directly in your local checkout.

Editors without dev container support (plain Vim, etc.) are not part of this workflow.

> **Warning**: A dev container isolates command execution, but no system is fully immune. With `--dangerously-skip-permissions`, a malicious project can still exfiltrate anything inside the container, including the credentials in `~/.claude`. Only use dev containers with trusted repositories. Do not mount host secrets such as `~/.ssh` or cloud credential files into the container.

## 1. Install prerequisites

- **Docker** — [install guide](https://docs.docker.com/engine/install/). Verify:

  ```bash
  docker --version
  docker run --rm hello-world
  ```

- **VS Code** + the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) (`ms-vscode-remote.remote-containers`).

New to dev containers? See the [VS Code Dev Containers tutorial](https://code.visualstudio.com/docs/devcontainers/tutorial).

## 2. Create `.devcontainer/devcontainer.json`

In your project repository, save:

```json
.devcontainer/devcontainer.json
{
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "features": {
    "ghcr.io/anthropics/devcontainer-features/claude-code:1.0": {}
  }
}
```

Notes:

- The [Claude Code Dev Container Feature](https://github.com/anthropics/devcontainer-features/tree/main/src/claude-code) installs the latest Claude Code; the CLI auto-updates inside the container by default.
- Replace the `image` with your project's base image, or remove it if your existing `devcontainer.json` uses a Dockerfile — just add the `features` block.
- If the build fails with `Failed to install Node.js and npm`, add `"ghcr.io/devcontainers/features/node:1": {}` to `features` (above the Claude Code entry) and rebuild.

## 3. Rebuild and open the container

1. Open the project folder in VS Code.
2. Command Palette: `Ctrl+Shift+P` (Mac: `Cmd+Shift+P`).
3. Run **Dev Containers: Reopen in Container** (first time) or **Dev Containers: Rebuild Container** (after editing `devcontainer.json`).
4. Wait for the image build to finish. VS Code now connects to the container.

Other tools: use the Dev Containers CLI ([devcontainers/cli](https://github.com/devcontainers/cli)) or your IDE's equivalent rebuild action.

## 4. Sign in to Claude Code

Open a terminal inside the container (`` Ctrl+` ``) and run:

```bash
claude
```

Follow the authentication prompt:

- **Anthropic**: browser sign-in with your Claude / Anthropic Console account. If the browser callback never reaches the container, copy the code shown in the browser and paste it at the `Paste code here if prompted` prompt in the terminal.
- **Bedrock / Vertex / Foundry**: cloud provider credentials are used — pass them as environment variables, never as mounted files.
- **API-provider setups (e.g. Z.AI)**: skip browser login entirely by setting env vars via `containerEnv`:

  ```json
  "containerEnv": {
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "YOUR_API_KEY"
  }
  ```

  For a non-interactive local variant without an editor, see [setup-isolated-zai.md](setup-isolated-zai.md).

## 5. Persist authentication across rebuilds (recommended)

By default the container home directory is discarded on rebuild, forcing a re-login every time. Claude Code stores auth, settings, and history in `~/.claude`, plus OAuth account and MCP servers in a separate `~/.claude.json`. Mount a named volume at `~/.claude` **and** point `CLAUDE_CONFIG_DIR` at it so `.claude.json` lands inside the volume too:

```json
"mounts": [
  "source=claude-code-config,target=/home/node/.claude,type=volume"
],
"containerEnv": {
  "CLAUDE_CONFIG_DIR": "/home/node/.claude"
}
```

Replace `/home/node` with the home directory of your container's `remoteUser`. To isolate state per project instead of sharing one volume across repos, use `source=claude-code-config-${devcontainerId}`.

## 6. Optional hardening

### Enforce organization policy

`/etc/claude-code/managed-settings.json` applies at the highest precedence on Linux. Copy it in from your Dockerfile:

```dockerfile
RUN mkdir -p /etc/claude-code
COPY managed-settings.json /etc/claude-code/managed-settings.json
```

Repo-level files can be edited by anyone with write access — for unbypassable policy use [server-managed settings](https://code.claude.com/docs/en/server-managed-settings) or MDM.

Set container-wide environment variables via `containerEnv`, e.g. disable telemetry and auto-update:

```json
"containerEnv": {
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
  "DISABLE_AUTOUPDATER": "1"
}
```

To pin a CLI version for reproducible builds, skip the feature and install from the Dockerfile: `RUN npm install -g @anthropic-ai/claude-code@X.Y.Z`.

### Restrict network egress

Limit outbound traffic to only the domains Claude Code needs — see [network access requirements](https://code.claude.com/docs/en/network-config#network-access-requirements). The [reference container](https://github.com/anthropics/claude-code/tree/main/.devcontainer) ships an `init-firewall.sh` example (requires `NET_ADMIN`/`NET_RAW` capabilities via `runArgs`); it is optional and not required by Claude Code itself.

### Run without permission prompts

Because the container runs as a non-root user, you can pass `--dangerously-skip-permissions` for unattended runs. The CLI rejects this flag as root — confirm `remoteUser` is non-root. Pair it with network egress restrictions. For fewer prompts without dropping safety checks, consider [auto mode](https://code.claude.com/docs/en/permission-modes#eliminate-prompts-with-auto-mode) instead.

## 7. Try the reference container

The [`anthropics/claude-code`](https://github.com/anthropics/claude-code/tree/main/.devcontainer) repo has a working example combining CLI + firewall + persistent volumes + Zsh shell:

```bash
git clone https://github.com/anthropics/claude-code
code claude-code
# In VS Code: Dev Containers: Reopen in Container
# Then in terminal: claude
```

To reuse it in your own project, copy its `.devcontainer/` directory and adjust the Dockerfile for your toolchain.

## Quick checklist

| Step | Action |
|------|--------|
| 1 | Install Docker + VS Code Dev Containers extension |
| 2 | Add `devcontainer.json` with the `claude-code` feature |
| 3 | Rebuild / reopen in container |
| 4 | Run `claude` in the container terminal, sign in |
| 5 | Mount volume + set `CLAUDE_CONFIG_DIR` to persist login |
| 6 | Optionally add managed settings, egress firewall, or auto mode |
