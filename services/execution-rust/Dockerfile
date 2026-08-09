FROM rust:1-bookworm AS build
WORKDIR /src
COPY services/execution-rust/Cargo.toml .
COPY services/execution-rust/src ./src
RUN cargo test --release && cargo build --release

FROM debian:bookworm-slim
RUN useradd -r -u 10001 quant
COPY --from=build /src/target/release/quant-execution-rust /usr/local/bin/quant-execution-rust
USER quant
EXPOSE 9100
ENTRYPOINT ["/usr/local/bin/quant-execution-rust"]
