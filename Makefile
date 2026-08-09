.PHONY: up down up-h1 up-shadow test e2e cpp-test rust-test
up:
	docker compose up --build
up-h1:
	docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
up-shadow:
	MARKET_MODE=shadow EXECUTION_MODE=shadow docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
down:
	docker compose down
test:
	PYTHONPATH=packages/quant:services/api pytest -q
e2e:
	PYTHONPATH=packages/quant:services/api pytest -q tests/test_e2e_shadow_h1.py
cpp-test:
	./scripts/build_cpp_local.sh
rust-test:
	cd services/execution-rust && cargo test --release
