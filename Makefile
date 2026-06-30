VENV := venv
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip
MAIN := main.py

GREEN   = \033[0;32m
YELLOW  = \033[0;33m
RESET   = \033[0m

.PHONY: install run debug clean lint lint-strict

install:
	@echo "$(GREEN)Installing dependencies...$(RESET)"
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt

run:
	$(PYTHON) $(MAIN) $(ARGS)

debug:
	@echo "$(YELLOW)Debugging program...$(RESET)"
	@$(PYTHON) -m pdb $(MAIN) $(ARGS)

clean:
	@echo "$(YELLOW)Cleaning build files...$(RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@rm -rf venv

lint:
	@flake8 .
	@mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	@flake8 .
	@mypy . --strict