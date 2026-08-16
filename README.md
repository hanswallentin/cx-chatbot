# Bookly Customer Support Agent

A customer support chat agent for Bookly, a fictional online bookstore. Handles order status, returns/refunds, and general policy questions (shipping, returns, password reset) through a real LLM (Anthropic Claude) with tool use, backed by a REST API and SQLite database, and fronted by a single-page chat UI.

## Architecture

```
frontend (nginx + static HTML/JS)
   |  POST /api/chat  (proxied)
   v
backend/orchestrator (FastAPI)
   |  conversation loop, session state, system prompt, guardrails
   |  Anthropic messages API (tool use)
   v
mcp-server (MCP tools over streamable-http)
   |  search_books, get_customer, find_customer_orders,
   |  get_order_status, initiate_return
   v
api (FastAPI REST layer — the only thing that touches the DB)
   v
db (SQLite: customers, books, orders)
```

Five services, five directories: [db/](db/), [api/](api/), [mcp-server/](mcp-server/), [backend/](backend/), [frontend/](frontend/). Each has its own `Dockerfile` and dependency manifest. [config.yaml](config.yaml) at the repo root centralizes everything non-secret (seed data, LLM model names, service URLs, policy text, guardrail categories); [.env](/.env) (from [.env.example](.env.example)) holds the actual secrets.

## Deployment

### Local (Docker Compose)

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY (optional — see "no API key" below)
docker compose up --build
```

This brings up, in order (enforced by `depends_on` + healthchecks): `db-init` (one-shot schema + seed) → `api` → `mcp-server` → `backend` → `frontend`. Open `http://localhost:8080`.

To reset everything (including the seeded database) and start clean:

```bash
docker compose down -v
docker compose up --build
```

### Commercial cloud (ECS, Azure Container Apps, a managed Compose/Kubernetes host)

The compose file is written to be portable with minimal change:

- Every inter-service address is an env var pointing at a **compose service name** (`http://api:8000`, `http://mcp-server:8100`), never `localhost` or a hard-coded IP. Any platform that preserves service-name DNS/service-discovery (ECS Service Connect, Azure Container Apps' internal ingress, Kubernetes Services) needs no changes here.
- All secrets and environment-specific values come in via environment variables, populated from `.env` locally and from the platform's secret manager (AWS Secrets Manager / Parameter Store, Azure Key Vault, etc.) in the cloud — `config.yaml` never holds a secret value itself, only the *name* of the env var that does (see "Configuration" below).
- `api`, `mcp-server`, `backend`, and `frontend` are stateless and can each run as multiple replicas behind a load balancer/ingress with no code change.
- **The one stateful piece is the database.** For a real deployment, swap the `db-init` + SQLite-volume setup for a managed Postgres instance (RDS, Cloud SQL, Azure Database for PostgreSQL): point `api`'s `DATABASE_PATH`/connection handling at the managed instance's connection string (injected as a secret), run the schema/seed once as a migration step instead of a `db-init` container, and drop the `dbdata` volume. `api/app/db.py` is the only file that would need a real driver swap (e.g. `psycopg`) since it's the only thing that touches the database.
- Container images built from these five `Dockerfile`s are what you push to your registry (ECR/ACR/GCR) — the compose file's `build:` stanzas become `image:` references pointing at the registry in a cloud-targeted compose variant, or get translated by your platform's compose-import tooling (e.g. the ECS CLI's `compose` integration).

## Setup

Prerequisites: Docker Engine + Docker Compose v2 (the `docker compose` CLI plugin, not the standalone `docker-compose` v1).

```bash
git clone <this repo>
cd cx-chatbot
cp .env.example .env
```

Fill in `.env`:
- `ANTHROPIC_API_KEY` — get one from the Anthropic Console. Without it, the backend starts in a mocked-response fallback mode (clearly logged) instead of crashing — fine for exercising the plumbing, but you won't get real conversations or real guardrail classification until a key is set.
- `DATABASE_PATH` / `LOG_LEVEL` — sane defaults are already set; only change if you know why.

First run seeds the database automatically — `db-init` runs once on `docker compose up`, creates the schema, and loads the seed data defined in `config.yaml`'s `seed:` section (customers, books, orders). There's nothing else to run by hand.

## Configuration

Everything non-secret lives in [config.yaml](config.yaml) at the repo root. Each service loads only the section(s) it needs at startup (via each service's own small `config.py`):

| Section | Used by | Controls |
|---|---|---|
| `database` | api, db-init | DB file path (env var name + default) |
| `services` | all | internal URLs/ports for inter-service calls |
| `llm` | backend | provider, main model, guardrail model, token/iteration limits |
| `logging` | all | log level (env var name + default) |
| `feature_flags` | backend | guardrails on/off, mock-LLM-fallback allowed |
| `mcp` | mcp-server, backend | tool names/descriptions (also drives the system prompt's tool list) |
| `policy` | backend | shipping/returns/password-reset FAQ text used in the system prompt |
| `guardrails` | backend | categories, sensitivity, decline message, logging |
| `seed` | db-init | customers/books/orders loaded on first run |

**Secrets are never in `config.yaml`.** Instead of a value, secret-bearing keys hold the *name* of an environment variable, e.g. `llm.api_key_env: ANTHROPIC_API_KEY`. The service reads `os.environ[<that name>]`, and the actual value comes from `.env` locally or your cloud provider's secret manager in production — the mapping in `config.yaml` doesn't change between environments, only where the env var's value comes from.

To override a value per environment without touching `config.yaml`: mount a different `config.yaml` (e.g. `config.prod.yaml`) at the same `/config.yaml` path via the `CONFIG_PATH` env var, or override specific env vars directly (e.g. set `MCP_SERVER_URL` to bypass `services.mcp_server.internal_url`).

## Testing

```bash
./scripts/test.sh
```

One command, no Docker required: creates/reuses a local `.venv`, installs all three services' dependencies, and runs the full `pytest` suite — API unit tests, MCP tool wrapper tests, and backend conversation + guardrail tests — against disposable fixtures/fakes. See `api/tests/`, `mcp-server/tests/`, `backend/tests/`.

The backend's conversation and guardrail tests use a scripted fake Anthropic client and a fake MCP client (see `backend/tests/fakes.py`) rather than live model calls, so they're deterministic and don't require `ANTHROPIC_API_KEY`. They specifically cover: a multi-turn return flow that only calls `initiate_return` once order/item/reason are all known, an order-status answer grounded in a tool result, a clarifying question when "my order" is ambiguous, and adversarial prompts (hate speech, violence, sexual content, drugs, off-topic) being blocked before ever reaching a tool call.

## FAQ

**How do I reset the database?**
`docker compose down -v` (the `-v` drops the named volume) then `docker compose up --build`. `db-init` recreates and reseeds it from `config.yaml`.

**How do I point this at a different LLM model?**
Edit `llm.model` (main conversation model) or `llm.guardrail_model` (classifier model) in `config.yaml` and restart the backend. No code change needed.

**How do I add a new book/customer/order?**
Add an entry under `seed.books` / `seed.customers` / `seed.orders` in `config.yaml`, then reset the database (see above). There's no admin UI in this prototype — seed data is the only way to add fixtures.

**Why isn't the agent calling a tool?**
Check the backend logs for `No ANTHROPIC_API_KEY resolved - running in mocked-LLM fallback mode` — in mock mode there's no real model, so nothing decides to call a tool. Otherwise, check that `mcp-server` is healthy (`docker compose ps`) and that the system prompt's tool list (built from `config.yaml`'s `mcp.tools`) matches what you expect — the model can only call tools it was told about.

**How do I run a single service outside Docker for debugging?**
Each service is a plain FastAPI (or, for mcp-server, a plain Python) app. From the repo root, with a venv containing that service's `requirements.txt` installed:
```bash
CONFIG_PATH=$(pwd)/config.yaml DATABASE_PATH=/tmp/bookly.db PYTHONPATH=api uvicorn app.main:app --app-dir api --port 8000
```
(swap ports/module paths for `mcp-server`/`backend`; set `API_BASE_URL`/`MCP_SERVER_URL` env vars to point at wherever those dependencies are running).

**How do I tune what the guardrails block?**
Edit `guardrails.categories` (add/remove/reword categories), `guardrails.sensitivity` (`strict`/`moderate`), or `guardrails.block_message` in `config.yaml`. No code change — the classifier prompt is built from these values at runtime.

**How do I run the test suite?**
`./scripts/test.sh` — see "Testing" above.

## Known limitations (prototype scope)

- Session state is in-memory in the backend process — restarting the backend or running multiple replicas loses/splits conversation history. A production version would move this to Redis or a similar shared store.
- No customer identity verification beyond "what email did you type" — a production version would authenticate the customer before disclosing order details.
- The guardrails classifier's judgment (not just its plumbing) can only be verified live, with a real `ANTHROPIC_API_KEY` configured — the automated test suite proves the wiring and fail-closed behavior deterministically, not the model's classification accuracy.
