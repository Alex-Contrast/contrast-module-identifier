"""EA entry point: identify which Contrast application corresponds to a repository.

Discovers modules, scores all against the Contrast org's app list,
and returns the single best match. Optional LLM fallback for low-confidence results.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .config import ContrastConfig
from .discover import discover_modules
from .mcp_contrast import ContrastMCP
from .models import DiscoveredModule
from .resolver import (
    AppCandidate, AppMatch, extract_search_term,
    resolve_module, score_candidate,
)

if TYPE_CHECKING:
    from .llm import LLMConfig

log = logging.getLogger(__name__)

# ---- Tuning constants ----
# Documented here so evals can reference and adjust them.
#
# DEFAULT_THRESHOLD: minimum confidence to accept a deterministic match.
#   0.7 for EA (higher than GA's 0.5) because single-shot — a wrong match
#   with no fallback is worse than "no match found."
#   Derived from: Jaccard(0.7) + language bonus(0.2) = 0.9 for strong partial,
#   exact match = 1.0, so 0.7 catches most real matches while rejecting noise.
#
# AMBIGUITY_FLOOR: if more than one candidate scores above this, the match
#   is ambiguous and LLM should disambiguate — even if the top score is 1.0.
#   0.6 chosen because: employee-management vs alex-employee-management both
#   score >=0.6 (Jaccard overlap + language bonus). Below 0.6 is noise.
#
# _LLM_CONFIDENCE_MAP: converts LLM categorical confidence to numeric so
#   AppMatch.confidence is always a float. Values are conservative —
#   HIGH=0.95 (not 1.0) because LLM matches are less certain than exact name hits.

DEFAULT_THRESHOLD = 0.7
AMBIGUITY_FLOOR = 0.6
_LLM_CONFIDENCE_MAP = {"HIGH": 0.95, "MEDIUM": 0.80, "LOW": 0.60}


def _best_deterministic_match(
    modules: list[DiscoveredModule],
    candidates: list[AppCandidate],
) -> Optional[AppMatch]:
    """Score every discovered module against all candidates, return the single best."""
    best: Optional[AppMatch] = None
    for module in modules:
        match = resolve_module(module, candidates, confidence_threshold=0.0)
        if match and (best is None or match.confidence > best.confidence):
            best = match
    return best


def _is_ambiguous(
    module: DiscoveredModule,
    candidates: list[AppCandidate],
    floor: float = AMBIGUITY_FLOOR,
) -> bool:
    """Check if multiple candidates score above the ambiguity floor for a module."""
    term = extract_search_term(module)
    strong = 0
    for c in candidates:
        if score_candidate(module, c, term) >= floor:
            strong += 1
            if strong > 1:
                return True
    return False


async def identify_repo(
    repo_path: str | Path,
    config: ContrastConfig,
    llm_config: "LLMConfig | None" = None,
    jar_path: str | None = None,
    confidence_threshold: float = DEFAULT_THRESHOLD,
) -> Optional[AppMatch]:
    """Identify the Contrast application for a repository.

    EA entry point: discovers modules (depth=2), scores all against the org's
    app list, returns the single best match.

    Args:
        repo_path: Path to repository.
        config: Contrast Security credentials.
        llm_config: LLM provider config. If None, no LLM fallback.
        jar_path: Path to mcp-contrast jar (falls back to Docker).
        confidence_threshold: Minimum confidence (default 0.7).

    Returns:
        AppMatch if found above threshold (or via LLM), None otherwise.
    """
    repo_path = Path(repo_path).resolve()

    # 1. Discover modules (shallow for EA)
    modules = discover_modules(repo_path, depth=2)
    log.info("Discovered %d modules in %s", len(modules), repo_path)
    for m in modules:
        log.info("  %s (%s) @ %s", m.name, m.ecosystem.value, m.path)

    # 2. Fetch org app list via MCP
    async with ContrastMCP(config, jar_path=jar_path) as mcp:
        candidates = await mcp.list_applications()
    log.info("Fetched %d Contrast applications", len(candidates))

    if not candidates:
        log.warning("No applications found in Contrast org")
        return None

    if not modules:
        # TODO: fall back to scoring repo directory name against candidates.
        # Deferred — most repos will have at least one manifest within depth=2.
        log.warning("No modules discovered in %s", repo_path)
        return None

    # 3. Score all modules, pick the best
    best = _best_deterministic_match(modules, candidates)

    if best:
        log.info(
            "Best deterministic: %s -> %s (%.0f%%, term='%s')",
            best.module.name, best.app_name,
            best.confidence * 100, best.search_term,
        )

    # 4. Above threshold and unambiguous — done
    # contrast_security.yaml is the strongest signal — skip ambiguity check
    from_yaml = best and best.module.contrast_app_name
    ambiguous = best and not from_yaml and _is_ambiguous(best.module, candidates)
    if ambiguous:
        log.info("Ambiguous match: multiple candidates above %.1f for %s", AMBIGUITY_FLOOR, best.module.name)
    if from_yaml:
        log.info("Match from contrast_security.yaml — skipping ambiguity check")

    if best and best.confidence >= confidence_threshold and not ambiguous:
        return best

    # 5. LLM fallback (below threshold OR ambiguous)
    if llm_config:
        from .llm.agent import resolve_module as llm_resolve

        target = best.module if best else modules[0]
        log.info("LLM fallback on: %s (%s)", target.name, target.path)

        llm_match = await llm_resolve(
            module=target,
            candidates=candidates,
            llm_config=llm_config,
            contrast_config=config,
            repo_path=str(repo_path),
            jar_path=jar_path,
        )

        if llm_match:
            return AppMatch(
                module=target,
                app_id=llm_match.application_id,
                app_name=llm_match.application_name,
                confidence=_LLM_CONFIDENCE_MAP.get(llm_match.confidence, 0.7),
                search_term=extract_search_term(target),
                source="llm",
            )

    # No confident match
    return None
