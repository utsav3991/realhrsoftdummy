.DEFAULT_GOAL := help
POETRY ?= poetry
NPM ?= npm
PORT ?= 8100
ARGS ?=
MANAGE = $(POETRY) run python manage.py
# The key and issuer an unchanged local Marketplace already trusts: it pins the key from
# its `realhrsoft_dev_token keygen` (REALHRSOFT_JWKS, issuer https://realhrsoft.dev.local).
DEV_KEY ?= $(HOME)/.realhrsoft-dev-key.pem
DEV_KID ?= realhrsoft-dev-1
DEV_ISSUER ?= https://realhrsoft.dev.local
MARKETPLACE ?= http://127.0.0.1:8000

.PHONY: help install env setup makemigrations migrate run deliver deliver-once retry dev \
	seed seed-keys seed-admin seed-clients seed-companies seed-employees demo \
	frontend-install frontend-build frontend-watch test check \
	marketplace-env sync-status reconcile reconcile-one company \
	keys keys-rotate keys-revoke use-dev-key env-dev

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Setup ---------------------------------------------------------------------------

install: ## Install Python and frontend dependencies
	$(POETRY) install --no-root $(ARGS)
	$(MAKE) frontend-install

env-dev: ## Create .env for the unchanged Marketplace (issuer DEV_ISSUER); then make use-dev-key
	@if [ -f .env ]; then echo ".env exists; left as is."; else \
		sed -e "s|^ISSUER=.*|ISSUER=$(DEV_ISSUER)|" \
			-e "s|^MARKETPLACE_URL=.*|MARKETPLACE_URL=$(MARKETPLACE)|" .env.example > .env; \
		echo "Created .env with ISSUER=$(DEV_ISSUER)."; fi

env: ## Create .env from .env.example with a fresh SNAPSHOT_API_TOKEN (never overwrites)
	@if [ -f .env ]; then echo ".env exists; left as is."; else \
		token=$$($(POETRY) run python -c "import secrets; print(secrets.token_urlsafe(32))"); \
		sed "s|^SNAPSHOT_API_TOKEN=.*|SNAPSHOT_API_TOKEN=$$token|" .env.example > .env; \
		echo "Created .env. Next: make marketplace-env"; fi

setup: ## First run: install, env, migrations, seed and build the employee screens
	$(MAKE) install
	$(MAKE) env
	$(MAKE) makemigrations
	$(MAKE) migrate
	$(MAKE) seed
	$(MAKE) frontend-build

makemigrations: ## Generate migrations for review
	$(MANAGE) makemigrations directory signing sync $(ARGS)

migrate: ## Apply migrations
	$(MANAGE) migrate $(ARGS)

# --- Run -----------------------------------------------------------------------------

run: ## Start the dummy on PORT (default 8100)
	$(MANAGE) runserver $(PORT) $(ARGS)

deliver: ## Keep delivering pending events to the Marketplace (retries included)
	$(MANAGE) deliver_events --loop $(ARGS)

deliver-once: ## Deliver what is due now, once
	$(MANAGE) deliver_events

retry: ## Requeue undelivered (pending or failed) events now and deliver them
	$(MANAGE) deliver_events --retry

dev: ## Run the server and the delivery loop together (Ctrl+C stops both)
	@trap 'kill 0' INT TERM EXIT; \
	$(MANAGE) deliver_events --loop & \
	$(MANAGE) runserver $(PORT)

# --- Demo data (create missing, publish, deliver; safe to rerun) ---------------------

seed: ## All seeders in dependency order, then show the logins
	$(MAKE) seed-keys
	$(MAKE) seed-admin
	$(MAKE) seed-clients
	$(MAKE) seed-companies
	$(MAKE) seed-employees
	$(MAKE) demo

seed-keys: ## RS256 signing keys for employee tokens and sync (if missing)
	$(MANAGE) signing_keys ensure

seed-admin: ## Superuser "admin"
	$(POETRY) run python scripts/seed_admin.py

seed-clients: ## Clients (Acme Group, Himalaya Holdings) and their HR users
	$(POETRY) run python scripts/seed_clients.py

seed-companies: ## Companies (organizations) of each client
	$(POETRY) run python scripts/seed_companies.py

seed-employees: ## Employee logins with their company employments
	$(POETRY) run python scripts/seed_employees.py

demo: ## Show demo logins, companies and RealHRSoft UUIDs
	@$(POETRY) run python scripts/show_demo.py

# --- Employee screens (Vue) ----------------------------------------------------------

frontend-install: ## Install the frontend (links ../realhrsoft-marketplace-employee-vue)
	cd frontend && $(NPM) install

frontend-build: ## Build the employee screens into portal/static/marketplace
	cd frontend && $(NPM) run build

frontend-watch: ## Rebuild the employee screens on change
	cd frontend && $(NPM) run watch

# --- Quality -------------------------------------------------------------------------

test: ## Run pytest; optionally ARGS="tests/test_proxy.py -q"
	$(POETRY) run pytest $(ARGS)

check: ## Django checks, tests and the frontend type check
	$(MANAGE) check
	$(POETRY) run pytest -q
	cd frontend && $(NPM) run type-check

# --- Marketplace (signed calls as RealHRSoft) ----------------------------------------

marketplace-env: ## Print the lines the Marketplace .env needs to trust this dummy
	@$(MANAGE) marketplace env

sync-status: ## Marketplace sync health: receipts, lag, problems
	$(MANAGE) marketplace status

reconcile: ## Ask the Marketplace for a full reconciliation
	$(MANAGE) marketplace reconcile

reconcile-one: ## One record: make reconcile-one SCOPE=employee TARGET=<uuid>
	$(MANAGE) marketplace reconcile --scope $(SCOPE) --target $(TARGET)

company: ## How the Marketplace mapped a company: make company UUID=<uuid>
	$(MANAGE) marketplace company $(UUID)

# --- Keys ----------------------------------------------------------------------------

use-dev-key: ## Sign tokens and deliveries with DEV_KEY as DEV_KID (no Marketplace change)
	$(MANAGE) signing_keys import --pem $(DEV_KEY) --kid $(DEV_KID)

keys: ## List signing keys
	$(MANAGE) signing_keys list

keys-rotate: ## New active key: make keys-rotate PURPOSE=employee|sync
	$(MANAGE) signing_keys rotate $(PURPOSE)

keys-revoke: ## Drop a key from the JWKS now: make keys-revoke KID=<kid>
	$(MANAGE) signing_keys revoke $(KID)
