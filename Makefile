# LLM Council Development Makefile
# Run `make help` to see available targets

.PHONY: help setup install test test-cov test-fast lint format typecheck docs docs-build clean dev-up dev-down

# Default target
.DEFAULT_GOAL := help

# Colors for help output
CYAN := \033[36m
RESET := \033[0m

help: ## Show this help message
	@echo "LLM Council Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-15s$(RESET) %s\n", $$1, $$2}'

# =============================================================================
# Setup & Installation
# =============================================================================

setup: ## Initial setup: install dependencies and create .env
	@echo "Installing dependencies..."
	uv sync --all-extras
	@if [ ! -f .env ]; then \
		echo "Creating .env from template..."; \
		cp .env.example .env; \
		echo "Please edit .env with your API keys"; \
	fi
	@echo ""
	@echo "Setup complete! Next steps:"
	@echo "  1. Edit .env with your API keys"
	@echo "  2. Run 'make test' to verify installation"

install: ## Install dependencies only (no .env creation)
	uv sync --all-extras

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=src --cov-report=html --cov-report=xml --cov-report=term-missing
	@echo ""
	@echo "Coverage report: htmlcov/index.html"

test-fast: ## Run tests excluding slow/integration tests
	uv run pytest tests/ -v -m "not slow and not integration"

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run linter (ruff check)
	uv run ruff check src/ tests/

format: ## Format code (ruff format)
	uv run ruff format src/ tests/

typecheck: ## Run type checker (mypy)
	uv run mypy src/llm_council --ignore-missing-imports

check: lint typecheck ## Run all code quality checks

fix: ## Auto-fix linting issues
	uv run ruff check src/ tests/ --fix
	uv run ruff format src/ tests/

# =============================================================================
# Documentation
# =============================================================================

docs: ## Serve documentation locally (live reload)
	uv run mkdocs serve

docs-build: ## Build documentation
	uv run mkdocs build

# =============================================================================
# Development Services
# =============================================================================

dev-up: ## Start development services (database, etc.)
	docker compose up -d

dev-down: ## Stop development services
	docker compose down

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Remove build artifacts and caches
	rm -rf dist/ build/ *.egg-info
	rm -rf .coverage htmlcov/ coverage.xml
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf site/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned build artifacts and caches"

# =============================================================================
# Release (maintainers only)
# =============================================================================

build: ## Build package
	uv build

publish-test: build ## Publish to TestPyPI
	uv publish --repository testpypi

publish: build ## Publish to PyPI (requires credentials)
	uv publish
