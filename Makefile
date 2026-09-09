.PHONY: install browsers temporal api worker ui discover replay test mcp stop

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

browsers:
	.venv/bin/playwright install chromium

temporal:
	temporal server start-dev

api:
	.venv/bin/capability-forge api

worker:
	.venv/bin/capability-forge worker

ui:
	cd frontend && npm run dev

discover:
	.venv/bin/capability-forge discover --goal "look up member 12345 and read their current savings balance"

replay:
	.venv/bin/capability-forge replay --latest --member-id 12345

replay-miss:
	.venv/bin/capability-forge replay --latest --member-id 99999

mcp:
	.venv/bin/capability-forge mcp

test:
	.venv/bin/pytest -q

stop:
	@-lsof -nP -tiTCP:8787,5173 -sTCP:LISTEN | xargs kill 2>/dev/null || true
	@-pkill -f "temporal server start-dev" 2>/dev/null || true
	@-pkill -f "capability-forge api" 2>/dev/null || true
	@echo "Stopped API (:8787), Vite (:5173), and Temporal if they were running."
