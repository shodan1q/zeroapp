#!/usr/bin/env bash
#
# Launcher for the round-the-clock app factory.
#
# Used both interactively and by the launchd agent. It resolves everything from
# the repository root rather than the caller's environment, because launchd
# starts processes with a near-empty environment and no working directory.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "No virtualenv at $PYTHON. Run 'make install' first." >&2
  exit 1
fi

LOG_DIR="$REPO_ROOT/data/factory"
mkdir -p "$LOG_DIR"

# DevEco Studio bundles the HarmonyOS SDK, hvigor, ohpm and Node. The builder
# discovers them itself, but putting the bundled Node on PATH also lets the
# generator syntax-check the JavaScript it produces.
DEVECO_CONTENTS="/Applications/DevEco-Studio.app/Contents"
if [[ -d "$DEVECO_CONTENTS" ]]; then
  export DEVECO_SDK_HOME="${DEVECO_SDK_HOME:-$DEVECO_CONTENTS/sdk}"
  export PATH="$DEVECO_CONTENTS/tools/node/bin:$DEVECO_CONTENTS/tools/ohpm/bin:$PATH"
fi

export PYTHONUNBUFFERED=1
exec "$PYTHON" -m zerodev.pipeline.daemon "$@"
