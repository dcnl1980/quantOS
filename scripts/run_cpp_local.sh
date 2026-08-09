#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/services/execution-cpp/build/quant-execution"
if [ ! -x "$BIN" ]; then "$ROOT/scripts/build_cpp_local.sh"; fi
exec "$BIN"
