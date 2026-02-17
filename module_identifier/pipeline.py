"""End-to-end pipeline: discover modules → resolve against Contrast → output mappings.

Two-phase resolution:
  1. Deterministic scoring (fast, free) — handles most cases
  2. LLM agent — investigates unmatched modules with MCP tools
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import ContrastConfig
from .discover import discover_modules
from .llm import LLMConfig, llm_resolve_modules
from .mcp_contrast import ContrastMCP
from .resolver import AppMatch, resolve_modules

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the full discovery + resolution pipeline."""
    matched: dict[str, AppMatch]      # module path → deterministic match
    unmatched: list[str]              # module paths with no match at all
    total: int
    llm_matched: dict[str, "LLMMatch"] = field(default_factory=dict)  # module path → LLM match


async def run(
    repo_path: str | Path,
    config: ContrastConfig,
    llm_config: LLMConfig,
    confidence_threshold: float = 0.5,
    depth: int = 4,
    jar_path: str | None = None,
) -> PipelineResult:
    """Discover modules in a repo and resolve them to Contrast app IDs.

    Args:
        repo_path: Path to the repository to scan.
        config: Contrast Security credentials.
        llm_config: LLM provider configuration for the fallback agent.
        confidence_threshold: Minimum score for deterministic matching.
        depth: Max directory depth for module discovery.
        jar_path: Optional path to mcp-contrast jar.

    Returns a PipelineResult with matched/unmatched/llm_matched modules.
    """
    t0 = time.monotonic()

    modules = discover_modules(Path(repo_path), depth=depth)
    log.info("Discovered %d modules in %s", len(modules), repo_path)
    for m in modules:
        log.info("  %s (%s) @ %s", m.name, m.ecosystem.value, m.path)

    async with ContrastMCP(config, jar_path=jar_path) as mcp:
        apps = await mcp.list_applications()

    # Phase 1: Deterministic scoring
    results = resolve_modules(modules, apps, confidence_threshold)

    matched = {path: match for path, match in results.items() if match is not None}
    unmatched_paths = [path for path, match in results.items() if match is None]

    elapsed_det = time.monotonic() - t0
    log.info("--- Deterministic phase (%.1fs) ---", elapsed_det)
    log.info("  %d/%d matched, %d unmatched", len(matched), len(modules), len(unmatched_paths))
    for path, match in matched.items():
        log.info("  ✓ %s → %s (%.0f%%)", path, match.app_name, match.confidence * 100)
    for path in unmatched_paths:
        log.info("  ✗ %s → no match", path)

    # Phase 2: LLM agent for unmatched modules
    llm_matched = {}
    if unmatched_paths:
        unmatched_modules = [m for m in modules if m.path in unmatched_paths]
        log.info("Running LLM agent on %d unmatched modules...", len(unmatched_modules))

        llm_results = await llm_resolve_modules(
            modules=unmatched_modules,
            candidates=apps,
            llm_config=llm_config,
            contrast_config=config,
            repo_path=str(repo_path),
            jar_path=jar_path,
            already_matched=matched,
        )

        llm_matched = {path: m for path, m in llm_results.items() if m is not None}
        still_unmatched = [path for path, m in llm_results.items() if m is None]

        elapsed_llm = time.monotonic() - t0 - elapsed_det
        log.info("--- LLM phase (%.1fs) ---", elapsed_llm)
        log.info("  %d/%d resolved by LLM", len(llm_matched), len(unmatched_modules))
        for path, m in llm_matched.items():
            log.info("  ✓ %s → %s (%s)", path, m.application_name, m.confidence)

        unmatched_paths = still_unmatched

    elapsed = time.monotonic() - t0
    log.info("--- Pipeline complete (%.1fs) ---", elapsed)

    return PipelineResult(
        matched=matched,
        unmatched=unmatched_paths,
        llm_matched=llm_matched,
        total=len(modules),
    )
