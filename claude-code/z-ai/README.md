# Claude Code + Z.AI (GLM)

Run Claude Code against **Z.AI's GLM models** instead of Anthropic's, by pointing the CLI at Z.AI's Anthropic-compatible API endpoint.

> **Prerequisite**: build the `claude-code` image first ([`../README.md`](../README.md) step 1). Z.AI setup reuses that image with different env vars.

## How it works

Claude Code reads two environment variables to redirect API traffic:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_BASE_URL` | Points the CLI at Z.AI instead of `api.anthropic.com` — set to `https://api.z.ai/api/anthropic` |
| `ANTHROPIC_AUTH_TOKEN` | Your Z.AI API key, used in place of Anthropic OAuth/API-key login |

Because the endpoint is Anthropic-compatible, no other part of the CLI changes — same commands, same UI. With these set, Claude Code skips browser sign-in entirely.

## Model mapping

Z.AI serves GLM models under its own names. Map Claude's model tiers to GLM models with:

```bash
ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.1
ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.1
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.5-air
```

Check Z.AI's model catalog for current GLM model IDs before using these — they change over time.

## Setup

Reuse the `claude-code` image and `docker run` pattern from [`../README.md`](../README.md), with a Z.AI env file and a separate credential volume so it never mixes with your normal Anthropic-auth volume.

### 1. Create the Z.AI env file

```bash
mkdir -p ~/.config/claude-zai
cat << 'EOF' > ~/.config/claude-zai/env
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
ANTHROPIC_AUTH_TOKEN=YOUR_ZAI_API_KEY
API_TIMEOUT_MS=3000000
ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.1
ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.1
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.5-air
EOF
chmod 600 ~/.config/claude-zai/env
```

Replace `YOUR_ZAI_API_KEY` with your real key. `chmod 600` keeps it readable only by you.

### 2. Run

```bash
PROJECT=$(basename $(pwd))
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-zai-config-$PROJECT:/home/node \
  --env-file ~/.config/claude-zai/env \
  --cap-drop=ALL \
  claude-code claude
```

Differences from the plain Anthropic run command in `../README.md`:

- `--env-file ~/.config/claude-zai/env` — injects the Z.AI base URL, auth token, and model mapping.
- `claude-zai-config-$PROJECT` — a **separate** named volume from `claude-code-config-$PROJECT`, so Z.AI credentials/settings never mix with an Anthropic-auth session for the same project.

No browser login prompt — the env-provided `ANTHROPIC_AUTH_TOKEN` authenticates immediately.

### Plugins, skills, memory (optional)

Same mounts as `../README.md` §4, added alongside the Z.AI flags above:

```bash
PROJECT=$(basename $(pwd))
AI_REPO=$HOME/dev/vdx-vn/ai
docker run -it --rm \
  -v $(pwd):/workspace \
  -v claude-zai-config-$PROJECT:/home/node \
  -v claude-plugins:/home/node/.claude/plugins \
  -v $AI_REPO/skills:/home/node/.claude/skills:ro \
  -v $AI_REPO/claude-code/CLAUDE.odoo.md:/home/node/.claude/CLAUDE.md:ro \
  -v $HOME/.claude-docker/settings.json:/home/node/.claude/settings.json \
  --env-file ~/.config/claude-zai/env \
  --cap-drop=ALL \
  claude-code claude --dangerously-skip-permissions
```

Swap `CLAUDE.odoo.md` for whatever memory file fits the project. See `../README.md` §4 for host-skills alternative, `:ro` rationale, and recommended plugin marketplaces.

### 3. Reset state

```bash
docker volume rm claude-zai-config-$PROJECT
```
