# =============================================================================
# Verixa — Makefile (mirror of ops.ps1 for unix/CI)
# =============================================================================
# Phony targets only; the real logic lives in ops.ps1 + Poetry/pnpm scripts.
# =============================================================================

.PHONY: help up down restart health test test-py test-ts lint \
        git-status git-log push db-migrate db-reset \
        compliance-check verify-mi300x install clean

REPO_ROOT := $(shell pwd)
COMPOSE_DIR := deploy/docker-compose

help:
	@echo "Verixa — Makefile"
	@echo ""
	@echo "Stack:"
	@echo "  make up           docker compose up -d"
	@echo "  make down         docker compose down"
	@echo "  make restart      down + up"
	@echo "  make health       hit every service healthcheck"
	@echo ""
	@echo "Tests:"
	@echo "  make test         all tests (pytest + vitest) at 100% gate"
	@echo "  make test-py      pytest only"
	@echo "  make test-ts      vitest only"
	@echo "  make lint         ruff + mypy + tsc"
	@echo ""
	@echo "Git:"
	@echo "  make git-status   git status --short"
	@echo "  make git-log      git log --oneline -20"
	@echo "  make push         git push origin main"
	@echo ""
	@echo "Install:"
	@echo "  make install      poetry install + pnpm install"
	@echo ""
	@echo "DB (after CP-3):"
	@echo "  make db-migrate   alembic upgrade head"
	@echo "  make db-reset     drop + recreate dev DB"
	@echo ""
	@echo "Verixa-specific:"
	@echo "  make verify-mi300x   ping MI300X reviewer endpoint"

install:
	poetry install
	pnpm install

up:
	cd $(COMPOSE_DIR) && docker compose up -d

down:
	cd $(COMPOSE_DIR) && docker compose down

restart: down up

health:
	@echo "[check] OPA";        @curl -fsS http://localhost:8181/health        > /dev/null && echo "[OK] opa"        || echo "[FAIL] opa"
	@echo "[check] Vault";      @curl -fsS http://localhost:8200/v1/sys/health > /dev/null && echo "[OK] vault"      || echo "[FAIL] vault"
	@echo "[check] MinIO";      @curl -fsS http://localhost:9000/minio/health/live > /dev/null && echo "[OK] minio" || echo "[FAIL] minio"
	@echo "[check] Prometheus"; @curl -fsS http://localhost:9090/-/healthy     > /dev/null && echo "[OK] prometheus" || echo "[FAIL] prometheus"
	@echo "[check] Postgres";   @nc -z localhost 5432 && echo "[OK] postgres" || echo "[FAIL] postgres"
	@echo "[check] Redis";      @nc -z localhost 6379 && echo "[OK] redis"    || echo "[FAIL] redis"

test: test-py test-ts

test-py:
	poetry run pytest

test-ts:
	cd packages/verixa-ts && pnpm test:coverage

lint:
	poetry run ruff check .
	cd packages/verixa-ts && pnpm typecheck

git-status:
	git status --short

git-log:
	git log --oneline -20

push:
	git push origin main

db-migrate:
	poetry run alembic upgrade head

db-reset:
	@echo "[WARN] drops dev DB"
	@read -p "Type YES to proceed: " ans && [ "$$ans" = "YES" ] || exit 1
	cd $(COMPOSE_DIR) && docker compose exec -T postgres psql -U verixa -d postgres -c "DROP DATABASE IF EXISTS verixa;"
	cd $(COMPOSE_DIR) && docker compose exec -T postgres psql -U verixa -d postgres -c "CREATE DATABASE verixa;"
	$(MAKE) db-migrate

verify-mi300x:
	@echo "Pinging MI300X reviewer endpoint..."
	@curl -fsS --max-time 10 http://165.245.133.120:8000/v1/models | head -c 400; echo

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov coverage .coverage
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
	cd packages/verixa-ts && rm -rf dist coverage .turbo node_modules/.cache 2>/dev/null || true
