# anno — self-documenting Makefile
# Run `make` or `make help` to list targets.
#
# Self-doc convention:
#   ## Section headers (bold in help)
#   target: ## description of the target

.DEFAULT_GOAL := help
.PHONY: help sync install hook test lint format pre-commit smoke help-cli json clean

UV ?= uv
RUN := $(UV) run
PYTEST := $(RUN) --with pytest --with-editable . pytest

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------

help: ## Show this help (default)
	@awk 'BEGIN {FS = ":.*?## "} \
	/^## / {sub(/^## /, ""); printf "\n\033[1m%s\033[0m\n", $$0; next} \
	/^[a-zA-Z0-9_ %-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' \
	$(MAKEFILE_LIST)
	@echo ""
	@echo "  Examples:"
	@echo "    make install"
	@echo "    make test"
	@echo "    make pre-commit"
	@echo ""

## Setup

sync: ## Create/update .venv and install package + dev deps
	$(UV) sync

hook: ## Install git pre-commit hook (ruff check + format)
	$(RUN) pre-commit install

install: sync hook ## Sync deps and install the pre-commit hook

## Quality

test: ## Run pytest
	$(PYTEST) -q

lint: ## ruff check (src + tests)
	$(RUN) ruff check src tests

format: ## ruff format (src + tests)
	$(RUN) ruff format src tests

pre-commit: ## Run pre-commit hooks on all files
	$(RUN) pre-commit run --all-files

smoke: ## CLI smoke (every leaf --help + each workflow path)
	$(PYTEST) -q tests/test_smoke.py

## CLI

help-cli: ## Print the anno command tree
	$(RUN) anno --help

json: ## Print the treeparse JSON schema (anno -j)
	$(RUN) anno -j

## Housekeeping

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache dist build
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -not -path './.venv/*' -exec rm -rf {} +
