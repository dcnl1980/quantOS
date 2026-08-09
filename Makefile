.PHONY: up down up-h1 up-shadow up-testnet test e2e e2e-h2 e2e-h3 e2e-h4 e2e-h5 cpp-test rust-test
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
cpp-test:
	./scripts/build_cpp_local.sh
rust-test:
	cd services/execution-rust && cargo test --release
