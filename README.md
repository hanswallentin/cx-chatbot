# Bookly Customer Support Agent

A customer support chat agent for Bookly, a fictional online bookstore. Handles order status, returns/refunds, and general policy questions (shipping, returns, password reset) through a real LLM (OpenAI) with tool use, backed by a REST API and SQLite database, and fronted by a single-page chat UI that collects the customer's name and email up front and greets them by name.

## Architecture

```
frontend (nginx + static HTML/JS)
   |  identity gate: name + email (validated), then POST /api/chat  (proxied)
   v
backend/orchestrator (FastAPI)
   |  conversation loop, session state, system prompt, guardrails
   |  OpenAI chat completions API (tool/function calling)
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
# edit .env and set OPENAI_API_KEY (optional — see "no API key" below)
docker compose up --build
```

This brings up, in order (enforced by `depends_on` + healthchecks): `db-init` (one-shot schema + seed) → `api` → `mcp-server` → `backend` → `frontend`.

**Accessing the app:** once `frontend` reports healthy (check with `docker compose ps`), open **http://localhost:8080** in a browser — that's the chat UI. The other services aren't meant to be opened directly, but are reachable for debugging: the backend's `/chat` and `/health` endpoints are published at `http://localhost:8200` (see `docker-compose.yml`'s `backend.ports`); `api` and `mcp-server` are internal-only by default (their `ports:` lines are commented out in `docker-compose.yml` — uncomment to expose `8000`/`8100` locally if you need to hit them directly).

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

## Prerequisites

Everything the chatbot itself needs (FastAPI, the OpenAI SDK, the MCP SDK, etc.) is declared in each service's `requirements.txt` and installed automatically inside its Docker image when you build the stack — you never install those by hand. What you need on your own machine is the tooling to build and run the containers, plus a couple of optional tools if you want to develop outside Docker.

### Required — to run the full stack

| Tool | Why | Check it's installed |
|---|---|---|
| **Docker Engine** (daemon running) | Builds and runs all 5 services | `docker --version` |
| **Docker Compose v2** (the `docker compose` CLI plugin — not standalone `docker-compose` v1) | Orchestrates the 5-service stack | `docker compose version` |
| **Git** | Clone this repo | `git --version` |

**macOS**
```bash
# pick one Docker runtime:
brew install --cask docker     # Docker Desktop (bundles Compose v2)
# or a lighter-weight alternative:
brew install --cask orbstack   # OrbStack (Docker-compatible, also bundles Compose v2)

brew install git                # only if `git --version` doesn't already work
```
Start Docker Desktop/OrbStack at least once (they run a background daemon) before `docker compose up`.

**Linux (Debian/Ubuntu)**
```bash
curl -fsSL https://get.docker.com | sudo sh   # installs Docker Engine + the Compose v2 plugin
sudo usermod -aG docker "$USER"               # run docker without sudo — log out/in afterward
sudo systemctl enable --now docker            # start the daemon and enable it on boot
sudo apt-get install -y git
```
Other distros: follow Docker's official install guide for your package manager (Fedora/RHEL: `dnf install docker docker-compose-plugin`; Arch: `pacman -S docker docker-compose`), then `systemctl enable --now docker`.

### Optional — for local development outside Docker

Only needed for `./scripts/test.sh` or running a single service directly with `uvicorn` (see the FAQ below) instead of through `docker compose`.

| Tool | Why | Check it's installed |
|---|---|---|
| **Python 3.12+** (with `venv` and `pip`, both bundled with a standard Python install) | `scripts/test.sh` creates a local virtualenv and runs the pytest suite | `python3 --version` |

**macOS**
```bash
brew install python@3.12
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt-get install -y python3 python3-venv python3-pip
```

## Setup

```bash
git clone <this repo>
cd cx-chatbot
cp .env.example .env
```

Fill in `.env`:
- `OPENAI_API_KEY` — get one from the OpenAI platform dashboard. Without it, the backend starts in a mocked-response fallback mode (clearly logged) instead of crashing — fine for exercising the plumbing, but you won't get real conversations or real guardrail classification until a key is set.
- `DATABASE_PATH` / `LOG_LEVEL` — sane defaults are already set; only change if you know why.

First run seeds the database automatically — `db-init` runs once on `docker compose up`, creates the schema, and loads the seed data defined in `config.yaml`'s `seed:` section (customers, books, orders). There's nothing else to run by hand.

Then bring the stack up and open the chat UI:

```bash
docker compose up --build
```

Once it's running, go to **http://localhost:8080** — that's the frontend.

## Session & identity

Every conversation starts with a small identity gate: the frontend asks for the customer's name and email before the chat opens, validates the email format client-side (a plain regex — this is a UX nicety, not an auth check), and only then reveals the chat with a personalized greeting ("Hi **Hans**! ... I have your email as *hans.wallentin@gmail.com*"). Each of the customer's own chat bubbles is tagged with their first name.

That name/email is sent to the backend alongside every `/chat` request (`customer_name`/`customer_email` on `ChatRequest`) and folded into the system prompt for that call only (see `Orchestrator._system_prompt_for` in `backend/app/orchestrator.py`) — so the agent already knows who it's talking to and won't ask for the email again mid-conversation. It's never written into persisted conversation history.

A **Log Out** button sits at the bottom of the chat window. It opens an "Are you sure?" confirmation; **Cancel** just closes it, **OK** clears the conversation, mints a new session ID, and returns to the identity gate for a fresh start. All of this is frontend/session state — logging out doesn't call any backend endpoint, it just abandons the old `session_id` (the backend's in-memory history for it simply becomes unreachable, see "Known limitations" below).

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
| `seed` | db-init | customers/books/orders loaded on first run (108 books, sourced from real Penguin Books UK bestseller/genre listings across 17 genres) |

**Secrets are never in `config.yaml`.** Instead of a value, secret-bearing keys hold the *name* of an environment variable, e.g. `llm.api_key_env: OPENAI_API_KEY`. The service reads `os.environ[<that name>]`, and the actual value comes from `.env` locally or your cloud provider's secret manager in production — the mapping in `config.yaml` doesn't change between environments, only where the env var's value comes from.

To override a value per environment without touching `config.yaml`: mount a different `config.yaml` (e.g. `config.prod.yaml`) at the same `/config.yaml` path via the `CONFIG_PATH` env var, or override specific env vars directly (e.g. set `MCP_SERVER_URL` to bypass `services.mcp_server.internal_url`).

## Testing

```bash
./scripts/test.sh
```

One command, no Docker required: creates/reuses a local `.venv`, installs all three services' dependencies, and runs the full `pytest` suite — API unit tests, MCP tool wrapper tests, and backend conversation + guardrail tests — against disposable fixtures/fakes. See `api/tests/`, `mcp-server/tests/`, `backend/tests/`.

The backend's conversation and guardrail tests use a scripted fake LLM client and a fake MCP client (see `backend/tests/fakes.py`) rather than live model calls, so they're deterministic and don't require `OPENAI_API_KEY`. They specifically cover: a multi-turn return flow that only calls `initiate_return` once order/item/reason are all known, an order-status answer grounded in a tool result, a clarifying question when "my order" is ambiguous, and adversarial prompts (hate speech, violence, sexual content, drugs, off-topic) being blocked before ever reaching a tool call. `backend/tests/test_openai_client.py` separately covers the OpenAI wire-format adapter itself (tool-call parsing, message/history translation) against a fake `AsyncOpenAI`-shaped client. `backend/tests/test_customer_context.py` covers the identity-gate integration point — that a known customer name/email gets folded into the system prompt per-call and never leaks into persisted history.

## FAQ

**How do I reset the database?**
`docker compose down -v` (the `-v` drops the named volume) then `docker compose up --build`. `db-init` recreates and reseeds it from `config.yaml`.

**How do I point this at a different LLM model?**
Edit `llm.model` (main conversation model) or `llm.guardrail_model` (classifier model) in `config.yaml` and restart the backend. No code change needed.

**How do I add a new book/customer/order?**
Add an entry under `seed.books` / `seed.customers` / `seed.orders` in `config.yaml`, then reset the database (see above). There's no admin UI in this prototype — seed data is the only way to add fixtures.

**Why isn't the agent calling a tool?**
Check the backend logs for `No OPENAI_API_KEY resolved - running in mocked-LLM fallback mode` — in mock mode there's no real model, so nothing decides to call a tool. Otherwise, check that `mcp-server` is healthy (`docker compose ps`) and that the system prompt's tool list (built from `config.yaml`'s `mcp.tools`) matches what you expect — the model can only call tools it was told about.

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

**How do I start over without reloading the page?**
Use the **Log Out** button at the bottom of the chat window, confirm "Are you sure?", and the frontend resets to the identity gate with a brand-new session ID — no page reload needed. See "Session & identity" above.

## Known limitations (prototype scope)

- Session state is in-memory in the backend process — restarting the backend or running multiple replicas loses/splits conversation history. A production version would move this to Redis or a similar shared store.
- No real customer identity verification — the frontend's identity gate collects a self-reported name/email (with client-side format checking only) before disclosing order details, not real authentication. A production version would verify identity before that trust boundary.
- The guardrails classifier's judgment (not just its plumbing) can only be verified live, with a real `OPENAI_API_KEY` configured — the automated test suite proves the wiring and fail-closed behavior deterministically, not the model's classification accuracy.
