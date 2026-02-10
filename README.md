# contrast-module-identifier

Deterministic module discovery and Contrast app ID resolution for code repositories. Scans a repo for modules, matches them to Contrast Security applications, and outputs `{module: app_id}` mappings.

## Architecture

```
discover_modules(repo)          # scan repo for modules (pom.xml, package.json, etc.)
    → resolve_modules(apps)     # score each module against org's Contrast app list
        → LLM fallback          # (planned) for modules scoring can't resolve
            → {module: app_id}  # final output
```

**Three-layer approach:**
1. **Deterministic discovery** — filesystem scan + manifest parsing. Finds modules by ecosystem (Java, Node, Python, Go, .NET, PHP). Extracts names from pom.xml, package.json, go.mod, etc.
2. **Deterministic scoring** — Jaccard token similarity + language alignment. Fetches org app list once via MCP, scores locally. `contrast_security.yaml` overrides manifest names when present.
3. **LLM fallback** — (not yet built) for modules where scoring falls below threshold.

## Usage

```python
import asyncio
from module_identifier.config import ContrastConfig
from module_identifier.pipeline import run

async def main():
    config = ContrastConfig.from_env()
    result = await run("/path/to/repo", config)

    for path, match in result.matched.items():
        print(f"{path} → {match.app_name} ({match.confidence:.0%})")

    for path in result.unmatched:
        print(f"{path} → no match (LLM fallback candidate)")

asyncio.run(main())
```

## Setup

```bash
pip install -e ".[dev]"
```

Requires a `.env` with Contrast credentials (see `.env.example`).

MCP server: uses `mcp-contrast` jar directly if available at `~/dev/aiml/mcp-contrast/target/mcp-contrast-*.jar`, falls back to Docker image.

## Tests

```bash
pytest module_identifier/tests/ -q
```

200 tests covering:
- Module discovery (scanner + declarations) across all ecosystems
- Name extraction from manifests
- Scoring (exact match, token overlap, language bonus)
- `contrast_security.yaml` override
- Golden dataset tests against real org data (1,317 apps, 6 languages)
- MCP response parsing

## What's done

- Module discovery: recursive scanner + declaration layer (Maven modules, Gradle includes, Node workspaces, .NET solutions)
- Search term extraction: strips `com.acme:`, `@scope/`, `github.com/org/` prefixes
- Scoring: Jaccard token similarity + language alignment, confidence threshold
- `contrast_security.yaml` support: overrides manifest name with declared Contrast app name
- MCP Contrast integration: fetch org app list, score locally
- Pipeline: discover → fetch → score → matched/unmatched output with logging
- Golden dataset: 1,317 real apps across Java, Node, Python, Go, .NET, PHP

## What's next

- LLM fallback for unmatched modules (single LLM call per unmatched module with candidates + context)
- Filter noise: utility scripts, test fixtures, tooling modules that will never be Contrast apps
