VENV ?= .venv
PYTHON ?= python3
BIN := $(VENV)/bin

.PHONY: install lint typecheck test check eval eval-drift demo
install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install -U pip setuptools wheel
	$(BIN)/python -m pip install -e '.[dev,mcp]'
lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
typecheck:
	$(BIN)/mypy
test:
	$(BIN)/pytest
check: lint typecheck test
eval:
	$(BIN)/codegraph eval
eval-drift: eval
	git diff --exit-code -- eval/reports
demo:
	$(BIN)/codegraph index tests/fixtures/mini
	$(BIN)/codegraph callers make --repo tests/fixtures/mini
	$(BIN)/codegraph inherits Shape --repo tests/fixtures/mini
