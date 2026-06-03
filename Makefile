.PHONY: help install install-all venv test test-fast lint format clean run-app run-cli init-db sample-pipeline

PY ?= /opt/homebrew/bin/python3.11
VENV = .venv
BIN = $(VENV)/bin

help:
	@echo "SmartApply AI — commandes disponibles"
	@echo ""
	@echo "  make venv             Cree un venv local"
	@echo "  make install          Installe le coeur (sans UI/PDF/Gmail)"
	@echo "  make install-all      Installe tout (UI + PDF + Gmail + dev)"
	@echo "  make init-db          Initialise la base SQLite"
	@echo "  make test             Lance les tests"
	@echo "  make test-fast        Tests rapides (skip integration)"
	@echo "  make lint             Verifie le code"
	@echo "  make format           Formate le code"
	@echo "  make run-app          Lance le dashboard Streamlit"
	@echo "  make run-cli          Lance la CLI (smartapply --help)"
	@echo "  make sample-pipeline  Lance un pipeline complet sur les samples"
	@echo "  make clean            Supprime caches et builds"

venv:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip wheel setuptools

install: venv
	$(BIN)/pip install -e ".[dev]"

install-all: venv
	$(BIN)/pip install -e ".[ui,pdf,gmail,dev]"

init-db:
	$(BIN)/python -m smartapply.cli init-db

test:
	$(BIN)/pytest

test-fast:
	$(BIN)/pytest -m "not integration and not llm"

lint:
	$(BIN)/ruff check smartapply tests

format:
	$(BIN)/ruff format smartapply tests
	$(BIN)/ruff check --fix smartapply tests

run-app:
	$(BIN)/streamlit run smartapply/app/main.py

run-cli:
	$(BIN)/python -m smartapply.cli --help

sample-pipeline:
	$(BIN)/python -m smartapply.cli pipeline --source samples

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info htmlcov .coverage
