.PHONY: up down test
up:
	docker compose up --build
down:
	docker compose down
test:
	PYTHONPATH=packages/quant pytest -q
