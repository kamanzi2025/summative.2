.PHONY: check lint format typecheck test schema

check: lint typecheck test schema  ## Everything CI runs

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy apps config manage.py

test:
	python manage.py check
	python manage.py makemigrations --check --dry-run
	python -m pytest -q

schema:
	python manage.py spectacular --file schema.yml --validate
	git diff --exit-code schema.yml
