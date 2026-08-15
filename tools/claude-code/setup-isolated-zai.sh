#!/usr/bin/env bash
set -Eeuo pipefail

# Claude Code + Z.AI isolated Docker launcher.
#
# Key properties:
# - Host ~/.claude is NEVER mounted into the runtime container.
# - Only selected reusable assets are copied into an isolated Docker volume.
# - Credentials, settings, history, session data, private keys, and secret-looking
#   files are excluded from the copy.
# - The current/project directory is the only host workspace mounted by default.

SCRIPT_NAME="$(basename "$0")"

PROJECT_DIR="$PWD"
HOST_CLAUDE_DIR="${HOME}/.claude"
CONFIG_DIR="${HOME}/.config/claude-zai"
ENV_FILE="${HOME}/.config/claude-zai/env"
IMAGE="claude-zai:local"
VOLUME="claude-zai-home"
READ_ONLY_PROJECT=0
REBUILD=0
NO_SYNC=0
RESET_VOLUME=0
DRY_RUN=0

# These directories are considered reusable Claude assets. They are copied
# recursively, subject to the sensitive-path and secret-content checks below.
SAFE_ASSET_DIRS=(skills commands agents rules)
EXTRA_ASSET_DIRS=()
CLAUDE_ARGS=()

usage() {
  cat <<USAGE
Usage:
  $SCRIPT_NAME [options] [-- <claude arguments>]

Examples:
  $SCRIPT_NAME --project ~/projects/my-odoo-project
  $SCRIPT_NAME --project . -- --print "Review this project"
  $SCRIPT_NAME --project . --read-only
  $SCRIPT_NAME --project .   # securely prompts for Z.AI key if needed

Options:
  --project PATH          Project folder to mount at /workspace.
                          Default: current directory.

  --host-claude-dir PATH  Source Claude directory used only for safe asset sync.
                          Default: ~/.claude

  --config-dir PATH       Local launcher configuration directory.
                          Default: ~/.config/claude-zai

  --env-file PATH         Z.AI environment file.
                          Default: ~/.config/claude-zai/env

  --image NAME            Docker image name.
                          Default: claude-zai:local

  --volume NAME           Docker volume for isolated /home/node.
                          Default: claude-zai-home

  --include-dir NAME      Also copy this directory from ~/.claude.
                          May be specified multiple times. Files are still
                          filtered for credential/secret patterns.

  --no-sync               Do not copy any assets from host ~/.claude.

  --read-only             Mount the project read-only.

  --rebuild               Rebuild the Docker image even if it already exists.

  --reset-volume          Delete and recreate the isolated Claude home volume.
                          This deletes the container-only Claude state.

  --dry-run               Show the Docker run command without starting Claude.

  -h, --help              Show this help.

Secret handling:
  The script does NOT accept an API key as a command-line option because command
  lines may be saved in shell history or exposed through process inspection.

  Preferred methods:
    1. Set ZAI_API_KEY in the environment for first-time setup.
    2. Let the script securely prompt for the key.
    3. Pre-create the env file with mode 600.
USAGE
}

log() {
  printf '[claude-zai] %s\n' "$*"
}

warn() {
  printf '[claude-zai] WARNING: %s\n' "$*" >&2
}

die() {
  printf '[claude-zai] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

canonical_dir() {
  local path="$1"
  [[ -d "$path" ]] || die "Directory does not exist: $path"
  (cd "$path" && pwd -P)
}

while (($#)); do
  case "$1" in
    --project)
      [[ $# -ge 2 ]] || die "--project requires a path"
      PROJECT_DIR="$2"
      shift 2
      ;;
    --host-claude-dir)
      [[ $# -ge 2 ]] || die "--host-claude-dir requires a path"
      HOST_CLAUDE_DIR="$2"
      shift 2
      ;;
    --config-dir)
      [[ $# -ge 2 ]] || die "--config-dir requires a path"
      CONFIG_DIR="$2"
      shift 2
      ;;
    --env-file)
      [[ $# -ge 2 ]] || die "--env-file requires a path"
      ENV_FILE="$2"
      shift 2
      ;;
    --image)
      [[ $# -ge 2 ]] || die "--image requires a name"
      IMAGE="$2"
      shift 2
      ;;
    --volume)
      [[ $# -ge 2 ]] || die "--volume requires a name"
      VOLUME="$2"
      shift 2
      ;;
    --include-dir)
      [[ $# -ge 2 ]] || die "--include-dir requires a directory name"
      EXTRA_ASSET_DIRS+=("$2")
      shift 2
      ;;
    --no-sync)
      NO_SYNC=1
      shift
      ;;
    --read-only)
      READ_ONLY_PROJECT=1
      shift
      ;;
    --rebuild)
      REBUILD=1
      shift
      ;;
    --reset-volume)
      RESET_VOLUME=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      CLAUDE_ARGS=("$@")
      break
      ;;
    *)
      die "Unknown option: $1 (use --help)"
      ;;
  esac
done

require_command docker
require_command find
require_command grep
require_command cp
require_command mkdir

PROJECT_DIR="$(canonical_dir "$PROJECT_DIR")"
CONFIG_DIR="$(mkdir -p "$CONFIG_DIR" && cd "$CONFIG_DIR" && pwd -P)"
[[ -n "$ENV_FILE" ]] || ENV_FILE="$CONFIG_DIR/env"
RUNTIME_DIR="$CONFIG_DIR/runtime"
SEED_DIR="$CONFIG_DIR/seed"

mkdir -p "$RUNTIME_DIR" "$SEED_DIR"

if ! docker info >/dev/null 2>&1; then
  die "Docker is installed but the daemon is not available to this user. Start Docker or fix Docker permissions."
fi

create_dockerfile() {
  cat > "$RUNTIME_DIR/Dockerfile" <<'DOCKERFILE'
FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        openssh-client \
        ripgrep \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@latest

RUN mkdir -p /home/node/.claude /workspace \
    && chown -R node:node /home/node /workspace

USER node
ENV HOME=/home/node
WORKDIR /workspace
ENTRYPOINT ["claude"]
DOCKERFILE
}

ensure_image() {
  create_dockerfile

  if ((REBUILD)) || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    log "Building Docker image: $IMAGE"
    docker build -t "$IMAGE" "$RUNTIME_DIR"
  else
    log "Using existing Docker image: $IMAGE"
  fi
}

ensure_env_file() {
  local env_dir
  env_dir="$(dirname "$ENV_FILE")"
  mkdir -p "$env_dir"

  if [[ -f "$ENV_FILE" ]] && grep -Eq '^ANTHROPIC_AUTH_TOKEN=.+$' "$ENV_FILE"; then
    chmod 600 "$ENV_FILE"
    log "Using existing Z.AI environment file: $ENV_FILE"
    return
  fi

  local api_key="${ZAI_API_KEY:-}"
  if [[ -z "$api_key" ]]; then
    if [[ ! -t 0 ]]; then
      die "No API key found. Set ZAI_API_KEY or create $ENV_FILE first."
    fi
    read -r -s -p 'Enter Z.AI API key: ' api_key
    printf '\n'
  fi

  [[ -n "$api_key" ]] || die "Z.AI API key cannot be empty"

  umask 077
  cat > "$ENV_FILE" <<EOF_ENV
ANTHROPIC_AUTH_TOKEN=$api_key
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
API_TIMEOUT_MS=3000000
ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.1
ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.1
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.5-air
EOF_ENV
  chmod 600 "$ENV_FILE"
  unset api_key
  log "Created protected Z.AI environment file: $ENV_FILE"
}

# Return success if a relative path is known to be sensitive or runtime/session data.
is_sensitive_path() {
  local rel="/$1/"
  local base
  base="$(basename "$1")"

  # Never copy these runtime/session/cache directories, even if they contain .md files.
  case "$rel" in
    */projects/*|*/session-env/*|*/shell-snapshots/*|*/history/*|*/cache/*|*/caches/*|*/logs/*|*/debug/*|*/statsig/*|*/telemetry/*|*/todos/*|*/backups/*)
      return 0
      ;;
  esac

  # Never copy common credential/config/key files.
  case "$base" in
    .env|.env.*|credentials|credentials.*|secrets|secrets.*|tokens|tokens.*|auth.json|oauth.json|settings.json|settings.local.json|history.jsonl|*.key|*.pem|*.p12|*.pfx|*.jks|*.keystore|*.kdbx)
      return 0
      ;;
  esac

  return 1
}

# Lightweight content scan. This cannot prove a file contains no secret, but catches
# common private-key/API-token cases without copying the source credential stores.
contains_obvious_secret() {
  local file="$1"

  # Ignore binary files for the text scan.
  if ! grep -Iq . "$file" 2>/dev/null; then
    return 1
  fi

  if grep -Eq -- '-----BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY-----' "$file"; then
    return 0
  fi

  if grep -Eiq -- "(ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|ZAI_API_KEY|OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|credential)[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9_./+=-]{16,}" "$file"; then
    return 0
  fi

  if grep -Eiq -- 'Authorization:[[:space:]]*Bearer[[:space:]]+[A-Za-z0-9._~+/=-]{16,}' "$file"; then
    return 0
  fi

  return 1
}

copy_one_safe_file() {
  local src="$1"
  local rel="$2"
  local dst="$SEED_DIR/.claude/$rel"

  if is_sensitive_path "$rel"; then
    return
  fi

  if contains_obvious_secret "$src"; then
    return
  fi

  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
}

copy_asset_tree() {
  local dir_name="$1"
  local src_dir="$HOST_CLAUDE_DIR/$dir_name"

  [[ -d "$src_dir" ]] || return 0

  while IFS= read -r -d '' file; do
    local rel="${file#"$HOST_CLAUDE_DIR/"}"
    copy_one_safe_file "$file" "$rel"
  done < <(find "$src_dir" -type f -print0)
}

copy_markdown_files() {
  [[ -d "$HOST_CLAUDE_DIR" ]] || return 0

  while IFS= read -r -d '' file; do
    local rel="${file#"$HOST_CLAUDE_DIR/"}"
    copy_one_safe_file "$file" "$rel"
  done < <(find "$HOST_CLAUDE_DIR" -type f \( -iname '*.md' -o -iname '*.markdown' \) -print0)
}

prepare_seed() {
  rm -rf "$SEED_DIR/.claude"
  mkdir -p "$SEED_DIR/.claude"

  if ((NO_SYNC)); then
    return
  fi

  if [[ ! -d "$HOST_CLAUDE_DIR" ]]; then
    return
  fi

  local dir
  for dir in "${SAFE_ASSET_DIRS[@]}" "${EXTRA_ASSET_DIRS[@]}"; do
    # --include-dir accepts a directory name/path relative to ~/.claude only.
    [[ "$dir" != /* && "$dir" != *".."* ]] || die "Unsafe --include-dir value: $dir"
    copy_asset_tree "$dir"
  done

  # Also preserve useful global instructions/docs such as CLAUDE.md, while
  # excluding project history/session/cache paths via is_sensitive_path().
  copy_markdown_files
}

reset_volume_if_requested() {
  if ((RESET_VOLUME)); then
    if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
      log "Removing isolated Claude volume: $VOLUME"
      docker volume rm "$VOLUME" >/dev/null
    fi
  fi

  docker volume create "$VOLUME" >/dev/null
}

sync_seed_to_volume() {
  ((NO_SYNC)) && return 0

  docker run --rm \
    --env-file "$ENV_FILE" \
    --network host \
    --user 0 \
    --entrypoint /bin/sh \
    -v "$VOLUME:/home/node" \
    -v "$SEED_DIR:/seed:ro" \
    "$IMAGE" \
    -c 'set -eu
        mkdir -p /home/node/.claude
        if [ -d /seed/.claude ]; then
          cp -a /seed/.claude/. /home/node/.claude/
        fi
        chown -R node:node /home/node'
}

run_claude() {
  local project_mount="$PROJECT_DIR:/workspace"
  if ((READ_ONLY_PROJECT)); then
    project_mount+=":ro"
  fi

  local safe_project_name
  safe_project_name="$(basename "$PROJECT_DIR" | tr -cs 'A-Za-z0-9_.-' '-')"
  safe_project_name="${safe_project_name#-}"
  safe_project_name="${safe_project_name%-}"
  [[ -n "$safe_project_name" ]] || safe_project_name="workspace"

  local container_name="claude-zai-${safe_project_name}-$$"

  local cmd=(
    docker run --rm -it
    --name "$container_name"
    --cap-drop=ALL
    --security-opt=no-new-privileges
    --env-file "$ENV_FILE"
    -v "$VOLUME:/home/node"
    -v "$project_mount"
    -w /workspace
    "$IMAGE"
    --dangerously-skip-permissions
  )

  if ((${#CLAUDE_ARGS[@]})); then
    cmd+=("${CLAUDE_ARGS[@]}")
  fi

  if ((DRY_RUN)); then
    printf 'Command:\n  '
    printf '%q ' "${cmd[@]}"
    printf '\n'
    return
  fi

  log "Starting isolated Claude Code"
  log "Project: $PROJECT_DIR -> /workspace$([[ $READ_ONLY_PROJECT -eq 1 ]] && printf ' (read-only)')"
  log "Claude home volume: $VOLUME -> /home/node"
  log "Host ~/.claude is NOT mounted into the runtime container"

  exec "${cmd[@]}"
}

main() {
  ensure_image
  ensure_env_file
  prepare_seed
  reset_volume_if_requested
  sync_seed_to_volume
  run_claude
}

main
