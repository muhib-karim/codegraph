VENV ?= .venv
PYTHON ?= python3
BIN := $(VENV)/bin

.PHONY: install lint typecheck test eval demo
install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -e '.[dev,mcp]'
lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
typecheck:
	$(BIN)/mypy
test:
	$(BIN)/pytest
eval:
	$(BIN)/codegraph eval
demo:
	$(BIN)/codegraph index tests/fixtures/mini
	$(BIN)/codegraph callers make --repo tests/fixtures/mini
	$(BIN)/codegraph inherits Shape --repo tests/fixtures/mini
