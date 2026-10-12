# Convenience wrappers: every target is one command from README, so `make` is optional.
COMPOSE_GPU := docker compose -f docker-compose.yml -f docker-compose.gpu.yml
VENV := .venv/bin

.DEFAULT_GOAL := help
.PHONY: help up up-gpu down logs ps test test-int eval lint fmt clean-check

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

up: ## Start the stack (CPU); first run downloads the model (~6.5 GB)
	docker compose up -d

up-gpu: ## Start the stack with an NVIDIA GPU for Ollama (needs nvidia-container-toolkit)
	$(COMPOSE_GPU) up -d

down: ## Stop the stack (keeps the model volume)
	docker compose down

logs: ## Follow API logs (JSON decision lines)
	docker compose logs -f api

ps: ## Show service status
	docker compose ps

test: ## Unit tests (no Docker)
	$(VENV)/pytest tests/unit -q

test-int: ## Integration tests against the running stack
	$(VENV)/pytest tests/integration -m integration -q

eval: ## Routing accuracy evaluation against the running stack (~3 min on CPU)
	$(VENV)/python eval/run_eval.py

lint: ## ruff check + format check + mypy
	$(VENV)/ruff check .
	$(VENV)/ruff format --check .
	$(VENV)/mypy app

fmt: ## Format and autofix with ruff
	$(VENV)/ruff format .
	$(VENV)/ruff check --fix .

clean-check: ## Cold start: deletes the model volume (CONFIRM=yes required)
ifneq ($(CONFIRM),yes)
	@echo "clean-check runs 'docker compose down -v' and deletes the downloaded model (~2.5 GB)." >&2
	@echo "Re-run with: make clean-check CONFIRM=yes" >&2
	@exit 1
endif
	docker compose down -v
	docker compose up -d
