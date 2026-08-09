#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cmake -S "$ROOT/services/execution-cpp" -B "$ROOT/services/execution-cpp/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$ROOT/services/execution-cpp/build" -j
ctest --test-dir "$ROOT/services/execution-cpp/build" --output-on-failure
echo "Binary: $ROOT/services/execution-cpp/build/quant-execution"
