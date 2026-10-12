# Ilera backend — reproducible local environment via uv.
#
# The containers (Dockerfile, Functions app) install from requirements.txt. `uv` locks
# that same file into requirements.lock and builds a Python 3.12 venv from the lock, so
# local == container: same interpreter (3.12, pinned in .python-version) and the same
# exact, hash-verified package versions.
#
# One-time: install uv -> https://docs.astral.sh/uv/  (curl -LsSf https://astral.sh/uv/install.sh | sh)

PYTHON_VERSION := 3.12

.PHONY: setup lock test run clean

## setup: create the .venv on Python 3.12 and install the locked dependencies + pytest.
setup:
	uv python install $(PYTHON_VERSION)
	uv venv --python $(PYTHON_VERSION)
	uv pip install --require-hashes -r requirements.lock
	uv pip install "pytest>=8.0.0,<9.0"
	@echo "Done. Run tests with: make test"

## lock: regenerate requirements.lock from requirements.txt (run after editing deps).
lock:
	uv pip compile requirements.txt --python-version $(PYTHON_VERSION) --generate-hashes -o requirements.lock
	@echo "requirements.lock updated — commit it, then run 'make setup' to apply."

## test: run the full test suite in the venv.
test:
	uv run pytest -q

## run: start the API locally against .env.
run:
	uv run uvicorn app.main:app --reload --port 8000

## clean: remove the local virtual environment.
clean:
	rm -rf .venv
