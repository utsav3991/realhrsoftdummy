# RealHRSoft dummy

For the production RealHRSoft team's implementation handoff, start with the
[integration contract](../realhrsoft-marketplace-integration-contract.md), its
[API reference](../realhrsoft-marketplace-integration-api-reference.md), and the
[OpenAPI export](../realhrsoft-marketplace-integration.openapi.json).

A small Django project that plays **RealHRSoft's side** of the Marketplace integration, so
the Marketplace can be developed and the pilot rehearsed without the real RealHRSoft. It
follows the contract in the Marketplace's
`docs/proposals/partner-client-hierarchy/implementation-plan.md` and the employee package
README (`realhrsoft-marketplace-employee-vue`).

| RealHRSoft duty | Here |
| --- | --- |
| Source of truth for clients, companies and employees | `directory` app, edited in the Django admin |
| Revision per aggregate, bumped on every published change | `sync/outbox.py` `publish` |
| Signed snapshot events with retries | `sync` outbox, `deliver_events` command |
| Snapshot API for reconciliation (bearer token) | `GET /api/marketplace-sync/v1/{partners,companies,employees}[/{uuid}]` |
| RS256 keys: one for employee tokens, one for sync; rotation and revocation | `signing` app, `signing_keys` command, admin actions |
| Public key set | `GET /.well-known/jwks.json` |
| Employee tokens with the issuance-time check | `signing/tokens.py` |
| Backend proxy for the web and mobile apps | `ANY /api/marketplace/<path>` (`portal/proxy.py`) |
| Employee login and company choice | `/login/`, `/` (with a tester that calls the proxy) |
| The Marketplace employee screens, mounted in RealHRSoft's own layout | `/marketplace/...` (the Vue package, built from `frontend/`) |

## Setup

`make help` lists every command. On a first run:

```bash
make setup     # install, .env (fresh SNAPSHOT_API_TOKEN), migrations, seed, build the screens
make dev       # server on :8100 plus the delivery loop (Ctrl+C stops both)
```

Or step by step: `make install`, `make env`, `make makemigrations`, `make migrate`,
`make seed`, `make frontend-build`, then `make run` and `make deliver` in two terminals.

With Docker, the whole system (this dummy, the Marketplace API, its workers and the web app)
runs from `../docker-compose.yml`: see `../DOCKER.md`. There the dummy uses PostgreSQL and
seeds with `docker compose run --rm dummy seed`.

## Demo directory (`make seed`)

The seeders run in dependency order. Each one creates what is missing (it never overwrites
your edits), publishes it, delivers the events to the Marketplace before it exits, and
reports what the Marketplace answered. Rerunning them is safe and publishes nothing new.
The data lives in `directory/demo.py`.

| Command | Creates |
| --- | --- |
| `make seed-keys` | RS256 keys for employee tokens and for sync |
| `make seed-admin` | Superuser `admin` |
| `make seed-clients` | Clients **Acme Group** and **Himalaya Holdings**, and their HR users |
| `make seed-companies` | Acme Retail, Acme Foods, Acme Logistics; Himalaya Hydro, Himalaya Tours |
| `make seed-employees` | Employee logins and their current employments |
| `make demo` | Prints every login with its RealHRSoft UUID |

Every login uses the password `demo-pass-123`.

| Login | Who | Notes |
| --- | --- | --- |
| `admin` | Superuser | The whole directory, keys and outbox at `/admin/` |
| `gita` | Acme Group HR | Contact person (the Marketplace invites them as client admin) |
| `anil`, `rita` | Himalaya Holdings HR | `anil` is the contact person |
| `ram` | Acme employee | Acme Retail and Acme Foods |
| `sita`, `maya` | Acme employees | Acme Retail; Acme Logistics |
| `bikash` | Acme employee | No current company, so no business access |
| `hari` | Acme, inactive | Former employee: RealHRSoft signs no tokens |
| `pema`, `suman` | Himalaya employees | Himalaya Hydro; Himalaya Tours |
| `nima` | Himalaya employee | Himalaya Hydro and Himalaya Tours |

**Client HR users** sign in to `/admin/` and see only their own client: its details, its
companies and its employees. They can add companies and employees (adding an employee also
creates their login), change employments, and activate or deactivate employees and
companies. They cannot deactivate their client, and they cannot see other clients, keys or
the outbox. To make someone a client HR user, a superuser adds them under Directory →
Client users (or on the client's page).

Resetting this database gives every record new UUIDs at revision 1. The Marketplace then
sees new clients, and the old ones stay there until it is reset too.

## Testing against an unchanged Marketplace

A local Marketplace set up with `realhrsoft_dev_token keygen` already pins that key
(`REALHRSOFT_JWKS`, kid `realhrsoft-dev-1`, issuer `https://realhrsoft.dev.local`). The
dummy can sign with the same key, so the Marketplace needs no change:

```bash
make env-dev            # .env with ISSUER=https://realhrsoft.dev.local (if .env is missing)
make makemigrations migrate
make use-dev-key        # imports ~/.realhrsoft-dev-key.pem for tokens and sync
make seed               # delivers clients, companies, employees
make sync-status        # what the Marketplace received and applied
make frontend-build && make dev
```

If `.env` already exists, set `ISSUER=https://realhrsoft.dev.local` and
`MARKETPLACE_URL=http://127.0.0.1:8000` in it. Run `make use-dev-key` before `make seed`:
otherwise the seed creates new keys, and the Marketplace rejects what they sign. In this
mode, reconciliation stays off (the Marketplace has no `REALHRSOFT_API_URL`), so seed in
order. The Marketplace still needs its Celery worker and beat to apply events.

## Connecting the Marketplace

1. `make marketplace-env` prints the lines for `realhrsoft-marketplace-rest-api/.env`:

   ```env
   REALHRSOFT_ISSUER=http://localhost:8100
   REALHRSOFT_JWKS=
   REALHRSOFT_JWKS_URL=http://localhost:8100/.well-known/jwks.json
   REALHRSOFT_API_URL=http://localhost:8100/api/marketplace-sync/v1
   REALHRSOFT_API_TOKEN=<this dummy's SNAPSHOT_API_TOKEN>
   ```

   Empty `REALHRSOFT_JWKS`, because a pinned key set wins over the URL.
2. Restart the Marketplace web server, **and run its Celery worker and beat**
   (`make worker`, `make beat` there). Events are received at once but applied by a beat
   task every 5 seconds. Without beat, receipts stay `pending`.
3. In the Marketplace, turn on `realhrsoft.sync` (Admin → RealHRSoft → Feature flags, or
   `scripts/set_feature_flags.py`). Until then, deliveries are refused and retried.
4. `make deliver-once` (or keep `make deliver` running) to send the events that are waiting.
   `make sync-status` shows what the Marketplace applied. `make reconcile` asks it to read
   everything again.
5. Turn on `realhrsoft.employee_access`, then sign in here as `ram` and open
   `/marketplace`.

## The employee screens (`frontend/`)

`frontend/` is a small Vite app that plays the RealHRSoft web host. It owns the app bar,
the company switcher, the account menu and the navigation drawer, and mounts the package's
routes under `/marketplace`. It installs the package from the tarball in `frontend/vendor/`
and imports its built `dist/`. After changing the sibling employee package, run
`npm run build` there, then `npm run vendor:employee` in `frontend/` and commit the
updated tarball and lockfile.

- `npm run build` writes to `portal/static/marketplace/`. Django's `/marketplace/...` view
  reads the Vite manifest and serves the app for every path (history routing). Before the
  first build, the page explains how to build.
- `npm run watch` rebuilds on every change; reload the page to see it.
- The page hands the app its context (employee, current companies, selected company, CSRF
  token) as `json_script`. It never includes a Marketplace token: the screens call
  `/api/marketplace`, the Django proxy.
- Changing company posts to `/company`, which checks that the employee currently works
  there and keeps the choice in the session, so the home page and the screens agree.
- `vite.config.ts` dedupes `vue`, `vue-router` and `vuetify`, because the linked package
  has its own `node_modules`. Without that, two copies of Vue would break the screens.

## Deploy Django and Vue on Vercel

Use the repository root (the directory containing `manage.py` and `vercel.json`)
as the Vercel Root Directory. The framework is Django. Clear any dashboard overrides
for the previous Vite install command, build command, and output directory so the
repository configuration applies.

The build installs the vendored frontend package and builds Vue into
`portal/static/marketplace/`, including the manifest read by Django. Vercel's Django
integration then runs `collectstatic` and serves the assets at `/static/` from its
CDN. Django serves login, admin, API routes and `/marketplace/...` on the same domain,
with the actual employee session and CSRF context. No standalone demo HTML is used.

Set these environment variables in Vercel before deploying:

| Variable | Value |
| --- | --- |
| `DEBUG` | `false` |
| `SECRET_KEY` | A generated secret, stable across deployments |
| `DATABASE_URL` | An external PostgreSQL connection URL; local SQLite is not persistent on Vercel |
| `ALLOWED_HOSTS` | Your exact deployment/custom hostnames, comma-separated, without `https://` |
| `CSRF_TRUSTED_ORIGINS` | The corresponding `https://` origins, comma-separated |
| `ISSUER` | The stable public URL of this Django app, matching the Marketplace configuration |
| `MARKETPLACE_URL` | The deployed Marketplace backend URL, without `/api` |
| `SNAPSHOT_API_TOKEN` | A generated secret shared with the Marketplace |
| `SYNC_DELIVER_ON_COMMIT` | `false`; background threads are not a reliable delivery worker on serverless hosting |

Keep preview deployments on a separate database and configure their hostnames and
origins too. Commit `frontend/vendor/*.tgz` and `frontend/package-lock.json` so a
fresh checkout can install the frontend without the sibling repository.

With the target database and integration environment variables loaded in a trusted
local shell, initialize it explicitly:

```bash
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
poetry run python manage.py signing_keys rotate employee
poetry run python manage.py signing_keys rotate sync
```

Migrations and demo seeders do not run automatically during builds. For demo data,
the existing `make seed` commands create accounts with the documented demo password.
Run `poetry run python manage.py deliver_events` against the deployed database to
deliver pending events; run `--loop` on a separate persistent worker if automatic
retries are needed. Vercel does not start this project's delivery loop.

After deployment, check `/login/`, `/admin/`, and `/marketplace` after signing in.
The Marketplace backend remains a separate service and must also be reachable.

## How it behaves

- **Publishing.** Saving a client, company or employee in the admin publishes it. The
  revision goes up only when the snapshot data changed, and the event is written in the
  same transaction. A background thread delivers it right after commit, and
  `deliver_events --loop` retries anything left over.
- **Records are never deleted.** Use the "Deactivate" admin action, which publishes
  `active: false` (the tombstone the Marketplace needs).
- **Delivery outcomes.** A 202 marks the event delivered and stores the Marketplace
  receipt. A 409 or 422 marks it failed, because resending the same bytes cannot help.
  A 401, 429, 5xx or network error is retried with backoff, up to 20 attempts. To requeue
  events, use the "Retry selected events now" action under Sync → Outbox events.
- **One client per employee.** Changing an employee's client ends their current
  employments under the old client when you save.
- **Tokens.** Each proxied call signs a fresh 60-second token. Before signing, the dummy
  re-checks that the employee and their login are active, that their client is active, and
  that the selected company is one they currently work for. Otherwise the proxy answers
  `403 EMPLOYEE_NOT_AUTHORIZED` without calling the Marketplace. The token asserts the
  published revision. If the Marketplace answers `409 AUTHORIZATION_CONTEXT_CHANGED`, the
  proxy signs a new token and retries once.
- **Key rotation.** `manage.py signing_keys rotate employee` (or `sync`) creates a new
  active key. The old key stays in the JWKS for 10 minutes. `signing_keys revoke <kid>`
  removes a key from the JWKS at once. After a compromise, the Marketplace should also
  list the kid in `REALHRSOFT_REVOKED_KIDS`.

Known gap: the snapshot API pages with a key cursor, not a database snapshot, so a
record that changes during a scan shows its newer revision. The Marketplace handles this
safely, but the real RealHRSoft should serve one consistent snapshot.

## Tests

```bash
poetry run pytest
```

The tests check tokens, signatures and payloads against the same verification rules the
Marketplace uses.
