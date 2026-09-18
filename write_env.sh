#!/usr/bin/env bash
set -euo pipefail

: "${APP_GITHUB_TOKEN:?}" "${MCP_TOKEN_SHA256:?}" "${ImageTag:?}"

# .env is line-based: collapse newlines so a multi-line value can't inject keys.
for k in DEFAULT_BRANCH DOCS_FOLDER_PATH MAX_FILE_TOKENS MCP_INSTRUCTIONS; do
  v=${!k:-}
  printf -v "$k" '%s' "${v//[$'\n\r']/ }"
done

umask 077
cat > .env <<EOF
GITHUB_TOKEN=${APP_GITHUB_TOKEN}
MCP_TOKEN_SHA256=${MCP_TOKEN_SHA256}
DEFAULT_BRANCH=${DEFAULT_BRANCH:-}
DOCS_FOLDER_PATH=${DOCS_FOLDER_PATH:-}
MAX_FILE_TOKENS=${MAX_FILE_TOKENS:-100000}
MCP_INSTRUCTIONS=${MCP_INSTRUCTIONS}
ImageTag=${ImageTag}
EOF
