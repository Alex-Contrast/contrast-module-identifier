# contrast-module-identifier

Identifies which Contrast Security application corresponds to a code repository. Scans the repo for modules, scores them against the org's Contrast app list, and returns the best match.

## How It Works

```
identify_repo(repo)
    ├── discover_modules(depth=2)     # find modules (pom.xml, package.json, etc.)
    ├── resolve_modules(apps)         # score all modules against Contrast app list
    ├── pick best match               # highest confidence wins
    └── LLM fallback                  # if below threshold or ambiguous, agent investigates
        → {app_id, app_name, confidence}
```

**Three layers:**
1. **Discovery** — filesystem scan + manifest parsing across 7 ecosystems (Java, Node, Python, Go, .NET, PHP, Ruby). `contrast_security.yaml` overrides manifest names when present.
2. **Deterministic scoring** — Jaccard token similarity + language alignment. Fetches org app list once via MCP, scores locally.
3. **LLM fallback** — Pydantic AI agent with filesystem + Contrast MCP tools for cases where scoring can't decide.

## Usage

```python
import asyncio
from module_identifier.config import ContrastConfig
from module_identifier.identify import identify_repo

from module_identifier.llm import LLMConfig

async def main():
    config = ContrastConfig.from_env()
    llm_config = LLMConfig.from_env()
    match = await identify_repo("/path/to/repo", config, llm_config)

    if match:
        print(f"{match.app_name} ({match.app_id})")
    else:
        print("No matching Contrast application found")

asyncio.run(main())
```

## Setup

```bash
pip install -e ".[dev]"
```

Requires a `.env` with Contrast credentials (see `.env.example`).

MCP server: jar path via `MCP_CONTRAST_JAR_PATH` env var, falls back to Docker `contrast/mcp-contrast:latest`.

## Tests

```bash
pytest module_identifier/tests/ -q
```

Covers:
- Module discovery (scanner + declarations) across all ecosystems
- Name extraction from manifests
- Scoring (exact match, token overlap, language bonus)
- `contrast_security.yaml` override
- Golden dataset tests against real org data (1,317 apps, 6 languages)
- MCP response parsing
- LLM agent (mocked, no real LLM calls)
