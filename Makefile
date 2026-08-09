.PHONY: up down up-h1 up-shadow up-testnet test e2e e2e-h2 e2e-h3 e2e-h4 e2e-h5 e2e-full cpp-test rust-test native-smoke validate
up:
	docker compose up --build
up-h1:
	docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
up-shadow:
	MARKET_MODE=shadow EXECUTION_MODE=shadow docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
up-testnet:
	EXECUTION_MODE=testnet TESTNET_VENUES=sim_a,sim_b docker compose up --build
down:
	docker compose down
test:
	PYTHONPATH=packages/quant:services/api pytest -q
e2e:
	PYTHONPATH=packages/quant:services/api pytest -q tests/test_e2e_shadow_h1.py
e2e-h2:
	PYTHONPATH=packages/quant:services/api pytest -q tests/test_h2_units.py tests/test_e2e_h2_execution.py
e2e-h3:
	PYTHONPATH=packages/quant:services/api pytest -q tests/test_h3_units.py tests/test_e2e_h3_research.py
e2e-h4:
	PYTHONPATH=packages/quant:services/api pytest -q tests/test_h4_units.py tests/test_e2e_h4_ontology.py
e2e-h5:
	PYTHONPATH=packages/quant:services/api pytest -q tests/test_h5_units.py tests/test_e2e_h5_copilot.py
e2e-full:
	PYTHONPATH=packages/quant:services/api pytest -q tests/test_core.py tests/test_h1_units.py tests/test_e2e_shadow_h1.py tests/test_h2_units.py tests/test_e2e_h2_execution.py tests/test_h3_units.py tests/test_e2e_h3_research.py tests/test_h4_units.py tests/test_e2e_h4_ontology.py tests/test_h5_units.py tests/test_e2e_h5_copilot.py tests/test_e2e_full_h0_h5.py
validate: e2e-full cpp-test rust-test
cpp-test:
	./scripts/build_cpp_local.sh
rust-test:
	cd services/execution-rust && cargo test --release
native-smoke:
	@BIN=services/execution-cpp/build/quant-execution; \
	if [ ! -x "$$BIN" ]; then ./scripts/build_cpp_local.sh; fi; \
	$$BIN & pid=$$!; \
	trap 'kill $$pid 2>/dev/null || true' EXIT; \
	for i in 1 2 3 4 5 6 7 8 9 10; do \
	  python3 -c "import socket;s=socket.create_connection(('127.0.0.1',9100),1);s.close()" 2>/dev/null && break; \
	  sleep 0.2; \
	done; \
	python3 scripts/smoke_native.py
