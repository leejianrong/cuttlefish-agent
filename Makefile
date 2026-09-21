.DEFAULT_GOAL := help
.PHONY: help dev lint type check test test-all test-sandbox-live ci install-hooks \
	frontend-install frontend-check frontend-build

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

# cuttlefish/sandbox's E2bSandboxProvider is tested against a real E2B account
# (docs/SLICES.md V2 test plan), the same cost-bearing posture kopicode's own
# paid `make bench` takes — never in CI, always an explicit, confirmed local run.
test-sandbox-live: ## create/exec/snapshot/destroy against a real E2B account — COSTS MONEY, never in CI
	@echo "This spends real E2B account time. Ctrl-C to abort."
	@read -r -p "continue? [y/N] " a; [ "$$a" = "y" ] || exit 1
	uv run pytest -m requires_e2b_credential -q

# The dashboard frontend (frontend/, ADR-0009) -- this repo's first non-Python
# build pipeline. `npm ci` (not `install`) so a stale lockfile fails loudly in CI
# rather than silently drifting, the same discipline `uv sync --frozen` already
# holds for the Python side.
frontend-install: ## npm ci in frontend/
	cd frontend && npm ci

frontend-check: ## svelte-check + tsc over frontend/ -- no build step
	cd frontend && npm run check

frontend-build: ## Production build of frontend/ to frontend/dist/
	cd frontend && npm run build

ci: check test-all frontend-check frontend-build ## Everything CI gates on (lint + mypy + full suite + frontend)

install-hooks: ## Install the pre-push git hook
	./scripts/install-hooks.sh
