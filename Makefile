.DEFAULT_GOAL := help
.PHONY: help dev lint type check test test-all ci install-hooks

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

dev: ## Sync the dev environment (uv sync)
	uv sync

lint: ## Ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

type: ## mypy --strict over src
	uv run mypy src

check: lint type ## Lint + type-check

test: ## Unit tests only — the fast inner-loop target, no infra
	uv run pytest tests/unit -q

# The kopicode delegation is tested against kopicode's own headless surface directly
# (docs/PLAN.md "Testing approach"), never a mock. Those tests need a real `kopicode`
# binary on PATH and skip themselves, rather than fail, when it's absent — the same
# posture satay-runtime's own studio-gated tests take for a missing extra.
test-all: ## The FULL suite (unit + integration + e2e)
	uv run pytest -q

ci: check test-all ## Everything CI gates on (lint + mypy + full suite)

install-hooks: ## Install the pre-push git hook
	./scripts/install-hooks.sh
