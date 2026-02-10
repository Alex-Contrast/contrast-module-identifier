"""End-to-end pipeline: discover modules → resolve against Contrast → output mappings."""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import ContrastConfig
from .discover import discover_modules
from .mcp_contrast import ContrastMCP
from .resolver import AppMatch, resolve_modules

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the full discovery + resolution pipeline."""
    matched: dict[str, AppMatch]      # module path → match
    unmatched: list[str]              # module paths with no match
    total: int


async def run(
    repo_path: str | Path,
    config: ContrastConfig,
    confidence_threshold: float = 0.5,
    depth: int = 4,
    jar_path: str | None = None,
) -> PipelineResult:
    """Discover modules in a repo and resolve them to Contrast app IDs.

    Returns a PipelineResult with matched/unmatched modules.
    """
    t0 = time.monotonic()

    modules = discover_modules(Path(repo_path), depth=depth)
    log.info("Discovered %d modules in %s", len(modules), repo_path)
    for m in modules:
        log.info("  %s (%s) @ %s", m.name, m.ecosystem.value, m.path)

    async with ContrastMCP(config, jar_path=jar_path) as mcp:
        apps = await mcp.list_applications()

    results = resolve_modules(modules, apps, confidence_threshold)

    matched = {path: match for path, match in results.items() if match is not None}
    unmatched = [path for path, match in results.items() if match is None]

    elapsed = time.monotonic() - t0
    log.info("--- Pipeline complete (%.1fs) ---", elapsed)
    log.info("  %d/%d matched, %d unmatched", len(matched), len(modules), len(unmatched))
    for path, match in matched.items():
        log.info("  ✓ %s → %s (%.0f%% confidence)", path, match.app_name, match.confidence * 100)
    for path in unmatched:
        log.info("  ✗ %s → no match", path)

    return PipelineResult(
        matched=matched,
        unmatched=unmatched,
        total=len(modules),
    )
