# CLAUDE.md

## Project Overview

**contrast-module-identifier** — Identifies which Contrast Security application corresponds to a code repository. Scans repos for software modules, scores them against the org's Contrast app list, and returns the best match as `{app_id, app_name, confidence}`.

This is the "Module ↔ App Name" linking strategy in Shane's Convergence of Source and Runtime architecture. EA ships repo-level resolution (one app per repo). GA adds module-level resolution (monorepo support, deferred to Shane's design).

Three-layer pipeline:
1. **Discovery** — filesystem scan + manifest parsing across 7 ecosystems
2. **Deterministic scoring** — Jaccard token similarity + language alignment
3. **LLM fallback** — Pydantic AI agent with MCP tools for low-confidence or ambiguous matches

## Quick Reference

```bash
# Install
pip install -e ".[dev]"

# Run tests
pytest module_identifier/tests/ -q

# Run the CLI
python -m module_identifier /path/to/repo

# CLI options: --threshold 0.5, --depth 4, --debug, -o/--output FILE, --single
```

## Project Structure

```
module_identifier/
├── __init__.py          # Public API: discover_modules, DiscoveredModule, Ecosystem, Manifest
├── __main__.py          # CLI entry point
├── identify.py          # identify_repo() — EA entry point (repo → single app_id)
├── config.py            # Contrast Security credentials (env vars)
├── models.py            # Core models: Ecosystem enum (7 langs), Manifest enum (25+ types), DiscoveredModule
├── scanner.py           # Recursive filesystem scanning, manifest detection, name extraction
├── declarations.py      # Explicit module declarations (Maven <modules>, Gradle include(), Node workspaces, .NET .sln)
├── discover.py          # Discovery orchestrator (declarations + scanner, deduplication)
├── resolver.py          # Search term extraction, Jaccard scoring, language bonus, resolution
├── mcp_contrast.py      # MCP client for Contrast Security API (list_applications)
├── pipeline.py          # Module-level pipeline: discover → resolve → LLM fallback (GA path)
├── llm/
│   ├── config.py        # Multi-provider LLM config (Bedrock, Anthropic, Gemini)
│   ├── models.py        # LLMMatch structured output model
│   ├── providers.py     # LLM model factory (lazy imports per provider)
│   ├── agent.py         # Pydantic AI agent with system prompt, MCP tools, usage limits
│   └── mcp_tools.py     # MCP toolset creation (Filesystem + Contrast, filtered tools)
└── tests/
    ├── fixtures/        # 25+ realistic directory structures + golden_apps.json (1,317 real apps)
    ├── test_scanner.py
    ├── test_declarations.py
    ├── test_discover.py
    ├── test_resolver.py
    ├── test_fixtures.py # Integration tests across all ecosystems
    ├── test_golden.py   # Golden dataset validation against real org data
    ├── test_mcp_contrast.py
    ├── test_pipeline_llm.py
    └── test_llm_*.py    # LLM subsystem tests (agent, config, mcp_tools, models, providers)
```

## Key Architecture Decisions

- **EA: score all, pick best**: discover modules (depth=2), score all against Contrast apps, return highest confidence match. No selection heuristic — the scorer decides.
- **Declaration-first discovery**: Declared modules (Maven, Gradle, Node workspaces, .NET solutions) take priority over scanner results
- **Ecosystem-specific name extraction**: Parses pom.xml (groupId:artifactId), package.json (name), go.mod (module path), pyproject.toml, composer.json, Gemfile, build.gradle(.kts)
- **Search term normalization**: Strips ecosystem prefixes — Maven `com.acme:order-api` → `order-api`, Node `@scope/billing-api` → `billing-api`, Go `github.com/acme/svc` → `svc`
- **Scoring**: Jaccard token similarity (max 0.7) + language bonus (+0.2) + exact match base (0.8). Max score 1.0. Default threshold 0.5
- **`contrast_security.yaml` override**: If present in a module directory, its `application.name` takes priority over manifest name
- **LLM agent constraints**: Max 10 requests, 15 tool calls. Message trimming keeps system + recent 10 messages
- **Multi-ecosystem tiebreaker**: Deferred to Shane's monorepo design for GA

## SmartFix Integration

SmartFix requires `CONTRAST_APP_ID` as an env var. This tool produces that value. In the pipeline (Docker), module-identifier runs as a pre-step before SmartFix.

## Dependencies

- `pydantic` >=2.0 — data validation and models
- `pydantic-ai` >=1.33.0 — LLM agent framework (structured output, tool calling, retries)
- `mcp` >=1.0 — Model Context Protocol client
- `python-dotenv` >=1.0 — environment variable loading
- `pytest` / `pytest-asyncio` — dev dependencies

Python 3.10+ required.

## Configuration

Contrast credentials via `.env` (see `.env.example`):
- `CONTRAST_HOST_NAME`, `CONTRAST_API_KEY`, `CONTRAST_SERVICE_KEY`, `CONTRAST_USERNAME`, `CONTRAST_ORG_ID`

LLM provider — set `AGENT_MODEL` with provider prefix (matches SmartFix):
- **Bedrock** (bearer token): `AGENT_MODEL=bedrock/<model-id>`, `AWS_REGION_NAME`, `AWS_BEARER_TOKEN_BEDROCK`
- **Bedrock** (IAM credentials): `AGENT_MODEL=bedrock/<model-id>`, `AWS_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- **Anthropic**: `AGENT_MODEL=anthropic/<model>`, `ANTHROPIC_API_KEY`
- **Gemini**: `AGENT_MODEL=gemini/<model>`, `GEMINI_API_KEY`

External services:
- **Contrast MCP server** — jar path via `MCP_CONTRAST_JAR_PATH` env var, falls back to Docker `contrast/mcp-contrast:latest`
- **Filesystem MCP** — `@modelcontextprotocol/server-filesystem@2025.11.25` (used by LLM agent)

## Testing

```bash
pytest module_identifier/tests/ -q           # All tests
pytest module_identifier/tests/test_golden.py # Golden dataset only
pytest module_identifier/tests/ -vv          # Verbose output
```

Test strategy:
- **Unit tests**: Individual functions (name extraction, scoring, tokenization, config validation)
- **Fixture-based integration**: 25+ realistic directory structures (monorepos, workspaces, malformed manifests, lock files)
- **Golden dataset**: 1,317 real Contrast apps across 6 languages — validates known correct mappings
- **LLM tests**: Agent context building, message trimming, provider factory (mocked, no real LLM calls)

pytest is configured with `asyncio_mode = "auto"` in pyproject.toml.

## E2E Verification (Contrast LLM Proxy)

Verifies the full pipeline end-to-end through the Contrast LLM proxy, including balance debit.

### Prerequisites

- Docker network `aiml-network` with `aiml-mysql` running (from aiml-services docker-compose)
- AWS Bedrock credentials in your shell environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`)
- Contrast credentials in `.env`

### 1. Start the LLM proxy

```bash
docker stop aiml-llm-proxy-api 2>/dev/null; docker rm aiml-llm-proxy-api 2>/dev/null

docker run -d --name aiml-llm-proxy-api \
  --network aiml-network \
  -p 9020:9020 -p 36006:16006 \
  -e SERVER_PORT=9020 \
  -e CONTRAST_ENVIRONMENT=local \
  -e MYSQL_HOST=aiml-mysql \
  -e MYSQL_PORT=3306 \
  -e MYSQL_SCHEMA=aiml_llm_proxy_api \
  -e SPRING_PROFILES_ACTIVE=docker,local \
  -e V2ENABLED=true \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" \
  -e AWS_REGION=us-east-1 \
  contrastsecurity-docker.jfrog.io/aiml-llm-proxy-api:local
```

Health check: `curl http://localhost:9020/actuator/health`

### 2. Run module-identifier

```bash
# Unset AGENT_MODEL to use contrast provider default
python -m module_identifier /path/to/test/repo
```

Known test repos: `~/dev/aiml/whackthecat`, `~/dev/employee-management`

### 3. Verify org debit in MySQL

```bash
mysql -h localhost -P 13306 -u contrast -p'default1!' aiml_llm_proxy_api
```

```sql
-- Recent balance transactions (org_id is BINARY(16) UUID)
SELECT HEX(organization_id) AS org_id, transaction_type,
       amount_nano_usd, balance_before_nano_usd, balance_after_nano_usd,
       request_id, created_at
FROM llm_balance_transaction
ORDER BY created_at DESC LIMIT 10;

-- Token usage per request
SELECT HEX(organization_id) AS org_id, user_id, model,
       input_tokens, output_tokens, cost_nano_usd, created_at
FROM llm_token_usage
ORDER BY created_at DESC LIMIT 10;

-- Current balance per org
SELECT HEX(organization_id) AS org_id, balance_nano_usd, updated_at
FROM llm_organization_balance;
```

### LLM Proxy Architecture Notes

- **Proxy URL pattern**: `https://{host}/api/llm-proxy/v2/organizations/{org_id}/anthropic` (matches contrast-triage)
- **API format**: Anthropic Messages API only — backed by AWS Bedrock
- **Supported models**: Claude (haiku-4-5, sonnet-4-5, sonnet-4-6, opus-4-5, opus-4-6) + Amazon Nova
- **v1 vs v2**: v1 hardcodes model from server config (legacy SmartFix). v2 respects client's model choice and tracks balance.
- **No OpenAI/Azure**: The proxy is Anthropic-format only. SmartFix accepts Azure keys in config but never uses them.

## Code Conventions

- Standard Python package layout with `pyproject.toml` (PEP 517)
- Dataclasses and Pydantic models for data structures
- Async throughout the pipeline (MCP client, LLM agent)
- Tests live inside the package at `module_identifier/tests/`
- Fixtures are realistic directory trees under `module_identifier/tests/fixtures/`
