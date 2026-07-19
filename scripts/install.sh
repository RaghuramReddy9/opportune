#!/usr/bin/env bash
set -euo pipefail

# One-command source installer for Ubuntu, macOS, and other Bash environments.
# Override these values when installing a different branch or location:
#   OPPORTUNE_REF=main OPPORTUNE_DIR="$HOME/opportune" bash install.sh

REPO_URL="${OPPORTUNE_REPO_URL:-https://github.com/RaghuramReddy9/opportune.git}"
REPO_REF="${OPPORTUNE_REF:-main}"
INSTALL_DIR="${OPPORTUNE_DIR:-$HOME/opportune}"

fail() {
  printf 'Opportune installation stopped: %s\n' "$1" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail "Git is required. Install Git and run this command again."

if ! command -v uv >/dev/null 2>&1; then
  command -v curl >/dev/null 2>&1 || fail "uv is missing and curl is not available to install it."
  printf 'uv was not found; installing it with the official installer...\n'
  curl -LsSf https://astral.sh/uv/install.sh | sh
  if [ -f "$HOME/.local/bin/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.local/bin/env"
  fi
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

command -v uv >/dev/null 2>&1 || \
  fail "uv was installed but is not available in this shell. Restart the shell and try again."

if [ -d "$INSTALL_DIR/.git" ]; then
  [ -z "$(git -C "$INSTALL_DIR" status --porcelain)" ] || \
    fail "$INSTALL_DIR has local changes. Save them before running the updater."
  current_ref="$(git -C "$INSTALL_DIR" branch --show-current)"
  [ "$current_ref" = "$REPO_REF" ] || \
    fail "$INSTALL_DIR is on '$current_ref'. Switch it to '$REPO_REF' before updating."
  printf 'Updating Opportune in %s...\n' "$INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only origin "$REPO_REF"
elif [ -e "$INSTALL_DIR" ]; then
  fail "$INSTALL_DIR exists but is not an Opportune Git checkout."
else
  printf 'Downloading Opportune into %s...\n' "$INSTALL_DIR"
  git clone --branch "$REPO_REF" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

printf 'Installing Python dependencies...\n'
(
  cd "$INSTALL_DIR"
  # Copy mode is reliable on cloud-synced folders and works everywhere.
  uv sync --frozen --link-mode copy
)

if [ "${OPPORTUNE_NO_RUN:-0}" = "1" ]; then
  printf 'Opportune is installed in %s\n' "$INSTALL_DIR"
  printf 'Start it with: cd %s && uv run opportune run\n' "$INSTALL_DIR"
  exit 0
fi

cd "$INSTALL_DIR"
exec uv run opportune run "$@"
