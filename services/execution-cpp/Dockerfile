FROM gcc:14-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends cmake && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY services/execution-cpp .
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
 && cmake --build build -j \
 && ctest --test-dir build --output-on-failure

FROM debian:bookworm-slim
RUN useradd -r -u 10001 quant
COPY --from=build /src/build/quant-execution /usr/local/bin/quant-execution
USER quant
EXPOSE 9100
ENTRYPOINT ["/usr/local/bin/quant-execution"]
