.PHONY: help install install-dev lint test test-unit test-integration test-e2e coverage clean validate-scenario

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -e .

install-dev: ## Install development dependencies
	pip install -e ".[dev]"

lint: ## Run linting checks
	ruff check src/ tests/
	ruff format --check src/ tests/
	mypy src/

format: ## Auto-format code
	ruff format src/ tests/
	ruff check --fix src/ tests/

test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v -m unit

test-integration: ## Run integration tests only
	pytest tests/integration/ -v -m integration

test-e2e: ## Run end-to-end tests only
	pytest tests/e2e/ -v -m e2e

test-safety: ## Run safety-critical tests
	pytest -v -m safety

coverage: ## Run tests with coverage report
	pytest tests/ --cov=src/chaoswopr --cov-report=html --cov-report=term-missing

validate-scenario: ## Validate a scenario YAML file (usage: make validate-scenario FILE=path/to/scenario.yaml)
	python -m chaoswopr.scenarios.validator $(FILE)

validate-exit-criteria: ## Run exit criteria validation
	python scripts/validate_exit_criteria.py

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

testnet-up: ## Launch the Ethereum testnet
	python -m chaoswopr.infrastructure.testnet.deployer up

testnet-down: ## Tear down the Ethereum testnet
	python -m chaoswopr.infrastructure.testnet.deployer down

testnet-status: ## Check testnet status
	python -m chaoswopr.infrastructure.testnet.deployer status
