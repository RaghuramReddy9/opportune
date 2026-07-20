#!/usr/bin/env bash
set -euo pipefail

VERSION="${OPPORTUNE_VERSION:-0.1.1}"
REPOSITORY="${OPPORTUNE_REPOSITORY:-RaghuramReddy9/opportune}"
BASE_URL="${OPPORTUNE_RELEASE_BASE_URL:-https://github.com/${REPOSITORY}/releases/download/v${VERSION}}"
WHEEL="opportune-${VERSION}-py3-none-any.whl"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/opportune-install.XXXXXX")"

cleanup() { rm -rf -- "$WORK_DIR"; }
fail() { printf 'Opportune installation stopped: %s\n' "$1" >&2; exit 1; }
trap cleanup EXIT

command -v curl >/dev/null 2>&1 || fail "curl is required to download the verified release."
if ! command -v uv >/dev/null 2>&1; then
  printf 'uv was not found; installing it with the official installer...\n'
  curl -LsSf https://astral.sh/uv/install.sh | sh
  [ ! -f "$HOME/.local/bin/env" ] || . "$HOME/.local/bin/env"
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || fail "uv is unavailable. Restart the shell and try again."

printf 'Downloading immutable Opportune v%s release artifacts...\n' "$VERSION"
curl -fL --proto '=https' --tlsv1.2 -o "$WORK_DIR/$WHEEL" "$BASE_URL/$WHEEL"
curl -fL --proto '=https' --tlsv1.2 -o "$WORK_DIR/SHA256SUMS" "$BASE_URL/SHA256SUMS"
EXPECTED="$(awk -v file="$WHEEL" '$2 == file || $2 == "*" file {print $1}' "$WORK_DIR/SHA256SUMS")"
[ -n "$EXPECTED" ] || fail "Checksum for $WHEEL is missing."
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum "$WORK_DIR/$WHEEL" | awk '{print $1}')"
else
  ACTUAL="$(shasum -a 256 "$WORK_DIR/$WHEEL" | awk '{print $1}')"
fi
[ "$ACTUAL" = "$EXPECTED" ] || fail "Checksum verification failed."
uv tool install --force "$WORK_DIR/$WHEEL"
printf 'Installed Opportune v%s. Start it with: opportune run\n' "$VERSION"
[ "${OPPORTUNE_NO_RUN:-0}" = "1" ] || exec opportune run "$@"
