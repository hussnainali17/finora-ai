.PHONY: setup up down logs ps test lint format check
setup:        ## create .env from template (edit CHANGE_ME values afterwards)
	@test -f .env || cp .env.example .env && echo ".env ready - replace CHANGE_ME values"
up:           ## build and start the full local stack
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f --tail=100
ps:
	docker compose ps
test:         ## run all test suites (requires local venv / node_modules)
	cd backend && pytest
	cd workers && pytest
	cd frontend && npm test
lint:
	cd backend && ruff check . && ruff format --check . && mypy app
	cd workers && ruff check . && ruff format --check . && mypy ca_workers
	cd frontend && npm run lint && npm run typecheck && npm run format:check
format:
	cd backend && ruff format . && ruff check --fix .
	cd workers && ruff format . && ruff check --fix .
	cd frontend && npm run format
check: lint test
