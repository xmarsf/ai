# Claude Code + Z.AI Environment Setup

This guide explains how to configure environment variables for running **Claude Code with Z.AI** inside the isolated Docker setup, and how to create a convenient `cc-glm` shortcut in `~/.bashrc`.

The setup assumes you already have:

```text
/home/xmars/dev/xmarsf/ai/tools/claude-code/setup-isolated-zai.sh
```

The launcher should run Claude Code inside Docker and mount the current project as `/workspace`.

---

## 1. Keep the Z.AI API Key Outside `.bashrc`

Do not hardcode your Z.AI API key directly in `~/.bashrc`.

Create a dedicated config directory:

```bash
mkdir -p ~/.config/claude-zai
```

Create the environment file:

```bash
nano ~/.config/claude-zai/env
```

Add:

```env
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
ANTHROPIC_AUTH_TOKEN=YOUR_ZAI_API_KEY
API_TIMEOUT_MS=3000000
```

Replace:

```text
YOUR_ZAI_API_KEY
```

with your real Z.AI API key.

Protect the file:

```bash
chmod 600 ~/.config/claude-zai/env
```

Check permissions:

```bash
ls -l ~/.config/claude-zai/env
```

Expected:

```text
-rw------- ...
```

This keeps the API key outside your shell config and outside your project repository.

---

## 2. Configure the `cc-glm` Shortcut in `~/.bashrc`

Open:

```bash
nano ~/.bashrc
```

Add:

```bash
cc-glm() {
  (
    export ANTHROPIC_DEFAULT_OPUS_MODEL="glm-5.2"
    export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5.1"
    export ANTHROPIC_DEFAULT_HAIKU_MODEL="glm-4.7-flash"

    # Optional marker for hooks/scripts.
    export CC_PROVIDER="glm"

    /home/xmars/dev/xmarsf/ai/tools/claude-code/setup-isolated-zai.sh \
      --project "$(pwd -P)"
  )
}
```

Reload your shell:

```bash
source ~/.bashrc
```

Now `cc-glm` can be used from any project directory.

---

## 3. How the Current Project Is Selected

The important part is:

```bash
--project "$(pwd -P)"
```

`pwd -P` returns the physical absolute path of your current directory.

For example:

```bash
cd ~/dev/project-a
cc-glm
```

passes approximately:

```bash
--project /home/xmars/dev/project-a
```

If you later run:

```bash
cd ~/dev/project-b
cc-glm
```

then the launcher receives:

```bash
--project /home/xmars/dev/project-b
```

So the same shortcut works for multiple projects without hardcoding a project path.

---

## 4. Why the Function Uses a Subshell

The function is wrapped in:

```bash
(
    ...
)
```

This starts a subshell.

Environment variables created inside it exist only while `cc-glm` is running.

After Claude Code exits, these values do not remain in your normal shell:

```text
ANTHROPIC_DEFAULT_OPUS_MODEL
ANTHROPIC_DEFAULT_SONNET_MODEL
ANTHROPIC_DEFAULT_HAIKU_MODEL
CC_PROVIDER
```

This keeps your normal terminal environment clean.

---

## 5. The Docker Launcher Must Forward the Variables

Exporting variables in `.bashrc` is not enough by itself.

Docker does not automatically copy every host environment variable into the container.

Your `setup-isolated-zai.sh` should contain a `docker run` command similar to:

```bash
docker run --rm -it \
    --env-file "$ENV_FILE" \
    --env ANTHROPIC_DEFAULT_OPUS_MODEL \
    --env ANTHROPIC_DEFAULT_SONNET_MODEL \
    --env ANTHROPIC_DEFAULT_HAIKU_MODEL \
    --env CC_PROVIDER \
    ...
```

The env file supplies:

```text
ANTHROPIC_BASE_URL
ANTHROPIC_AUTH_TOKEN
API_TIMEOUT_MS
```

The `--env` arguments forward the model mappings from the `cc-glm` function.

A typical launcher section looks like:

```bash
docker run --rm -it \
    --env-file "$ENV_FILE" \
    --env ANTHROPIC_DEFAULT_OPUS_MODEL \
    --env ANTHROPIC_DEFAULT_SONNET_MODEL \
    --env ANTHROPIC_DEFAULT_HAIKU_MODEL \
    --env CC_PROVIDER \
    -v "$VOLUME_NAME:/home/node" \
    -v "$PROJECT_DIR:/workspace" \
    -w /workspace \
    "$IMAGE_NAME"
```

If the launcher already uses:

```bash
--env-file ~/.config/claude-zai/env
```

then you do not need to export the API key from `.bashrc`.

---

## 6. Recommended Environment Structure

```text
~/.config/claude-zai/env
│
├── ANTHROPIC_BASE_URL
├── ANTHROPIC_AUTH_TOKEN
└── API_TIMEOUT_MS
         │
         │ --env-file
         ▼
┌───────────────────────────┐
│      Docker Container     │
│                           │
│       Claude Code         │
│        via Z.AI           │
└───────────────────────────┘
         ▲
         │ --env
         │
~/.bashrc
│
└── cc-glm()
    ├── OPUS   = glm-5.2
    ├── SONNET = glm-5.1
    ├── HAIKU  = glm-4.7-flash
    └── CC_PROVIDER=glm
```

The responsibilities are separated cleanly:

```text
Credentials     -> ~/.config/claude-zai/env
Model selection -> ~/.bashrc
Container logic -> setup-isolated-zai.sh
Project path    -> current working directory
```

---

## 7. Verify Variables Inside the Container

After running:

```bash
cc-glm
```

check the environment inside the container:

```bash
printenv | grep -E 'ANTHROPIC_(BASE_URL|DEFAULT_)|CC_PROVIDER'
```

Expected output should look similar to:

```text
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.2
ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.1
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.7-flash
CC_PROVIDER=glm
```

Do not print `ANTHROPIC_AUTH_TOKEN` because it contains your API key.

You can verify that the token exists without displaying it:

```bash
if [ -n "$ANTHROPIC_AUTH_TOKEN" ]; then
    echo "ANTHROPIC_AUTH_TOKEN is configured"
else
    echo "ANTHROPIC_AUTH_TOKEN is missing"
fi
```

---

## 8. Verify the Model in Claude Code

Start Claude Code:

```bash
cc-glm
```

Then use:

```text
/model
```

or:

```text
/status
```

The custom model mappings should correspond to:

```text
Opus   -> glm-5.2
Sonnet -> glm-5.1
Haiku  -> glm-4.7-flash
```

If Claude Code still shows older mappings, first verify the variables inside the container.

Also inspect the isolated Claude configuration:

```bash
cat ~/.claude/settings.json
```

A persistent Docker volume may contain old model mappings from a previous run.

---

## 9. Optional 1M Context Profile

If your Z.AI account and Claude Code version support the 1M-context model syntax, you can use another shortcut:

```bash
cc-glm-long() {
  (
    export ANTHROPIC_DEFAULT_OPUS_MODEL="glm-5.2[1m]"
    export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5.2[1m]"
    export ANTHROPIC_DEFAULT_HAIKU_MODEL="glm-4.7-flash"
    export CLAUDE_CODE_AUTO_COMPACT_WINDOW="1000000"
    export CC_PROVIDER="glm"

    /home/xmars/dev/xmarsf/ai/tools/claude-code/setup-isolated-zai.sh \
      --project "$(pwd -P)"
  )
}
```

If you use this, also forward:

```bash
--env CLAUDE_CODE_AUTO_COMPACT_WINDOW
```

in the Docker command.

---

## 10. Common Daily Workflow

Move into a project:

```bash
cd ~/dev/my-project
```

Start Claude Code:

```bash
cc-glm
```

The flow is:

```text
Current directory
      │
      │ $(pwd -P)
      ▼
setup-isolated-zai.sh
      │
      ├── reads Z.AI credentials from ~/.config/claude-zai/env
      │
      ├── receives model variables from cc-glm()
      │
      ├── mounts current directory as /workspace
      │
      └── starts isolated Docker container
                    │
                    ▼
               Claude Code
                 via Z.AI
```

When Claude Code exits:

```text
Container                     -> removed
Docker image                  -> preserved
Docker volume /home/node      -> preserved
Container ~/.claude           -> preserved in the Docker volume
Host project                  -> preserved
Host ~/.claude                -> never mounted
Z.AI credentials env file     -> preserved on host
```

---

## Recommended Final Configuration

### `~/.config/claude-zai/env`

```env
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
ANTHROPIC_AUTH_TOKEN=YOUR_ZAI_API_KEY
API_TIMEOUT_MS=3000000
```

Protect it:

```bash
chmod 600 ~/.config/claude-zai/env
```

### `~/.bashrc`

```bash
cc-glm() {
  (
    export ANTHROPIC_DEFAULT_OPUS_MODEL="glm-5.2"
    export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5.1"
    export ANTHROPIC_DEFAULT_HAIKU_MODEL="glm-4.7-flash"
    export CC_PROVIDER="glm"

    /home/xmars/dev/xmarsf/ai/tools/claude-code/setup-isolated-zai.sh \
      --project "$(pwd -P)"
  )
}
```

Reload:

```bash
source ~/.bashrc
```

Run from any project:

```bash
cd /path/to/project
cc-glm
```

This keeps credentials separate, automatically uses the current directory as the mounted project, and lets you control the Z.AI model mapping cleanly from your shell shortcut.
