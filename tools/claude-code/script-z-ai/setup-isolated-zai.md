# Claude Code + Z.AI Environment Setup

This guide explains how to configure environment variables for running **Claude Code with Z.AI** inside an isolated Docker setup.

## 1. Setup Z.AI Credentials

Create a secure environment file for your API key:

```bash
mkdir -p ~/.config/claude-zai
cat << 'EOF' > ~/.config/claude-zai/env
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
ANTHROPIC_AUTH_TOKEN=YOUR_ZAI_API_KEY
API_TIMEOUT_MS=3000000
API_TIMEOUT_MS=3000000
ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.3[1m]
ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.3[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.7
EOF

chmod 600 ~/.config/claude-zai/env
```

*(Replace `YOUR_ZAI_API_KEY` with your actual key)*

## 2. Create Shell Shortcut

Add this shortcut to your `~/.bashrc` (or `~/.zshrc`) to easily launch Claude Code from any project directory:

```bash
cc-glm() {
  (
    /home/xmars/dev/xmarsf/ai/tools/claude-code/setup-isolated-zai.sh \
      --project "$(pwd -P)"
  )
}
```

Reload your shell:

```bash
source ~/.bashrc
```

## 3. Usage

Simply navigate to any project directory and run the shortcut. Your current directory will automatically be mounted as `/workspace` inside the Docker container.

```bash
cd ~/dev/my-project
cc-glm
```
