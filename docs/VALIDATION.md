# Validation report

Generated product validation performed in the build environment.

## Python
- all Python files parsed successfully
- core pytest suite: 5/5 passed

## C++20
Compiler: GCC 14.2
Build type: Release

- CMake configure: passed
- native binary build: passed
- CTest: passed
- TCP PING: passed
- SNAPSHOT: passed
- positive paired paper execution: passed
- portfolio mutation: passed
- RESET: passed
- 2,000-request local benchmark: passed

One observed build-environment run produced approximately:
- internal decision median: ~60 ns
- internal decision p95: ~250 ns
- localhost persistent TCP median RTT: ~0.40 ms
- localhost persistent TCP p95 RTT: ~0.63 ms

These figures are **not exchange latency benchmarks** and should not be used as expected production trading performance.
They measure a tiny in-memory risk/execution calculation and local process-to-process TCP on the build host.

## Rust
The Rust implementation is protocol-compatible in source and contains unit tests. Its Dockerfile runs:

```text
cargo test --release
cargo build --release
```

The artifact build environment used to generate this ZIP did not contain a Rust toolchain or Docker daemon, so the
Rust target could not be compiled locally during packaging. The default product path is therefore the independently
compiled and smoke-tested C++20 engine.
