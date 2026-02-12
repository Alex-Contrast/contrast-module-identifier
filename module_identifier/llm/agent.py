"""LLM fallback agent for resolving modules that the deterministic scorer couldn't match."""

import logging
import time
from typing import Optional

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import ModelMessage

from ..config import ContrastConfig
from ..models import DiscoveredModule
from ..resolver import AppCandidate, AppMatch
from .config import LLMConfig
from .models import LLMMatch
from .mcp_tools import create_mcp_toolsets
from .providers import get_model

log = logging.getLogger(__name__)

# Agent limits — match app-identifier defaults
MAX_MODEL_REQUESTS = 10
MAX_TOOL_CALLS = 15
MAX_MESSAGES_BEFORE_TRIM = 20
MESSAGES_TO_KEEP_AFTER_TRIM = 10

# How many top candidates to include in agent context
TOP_N_CANDIDATES = 5


def _trim_messages(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Keep first message (system) + most recent messages."""
    if len(messages) > MAX_MESSAGES_BEFORE_TRIM:
        return messages[:1] + messages[-MESSAGES_TO_KEEP_AFTER_TRIM:]
    return messages


AGENT_INSTRUCTIONS = """
You are resolving a code module to its Contrast Security application.

The deterministic scorer could not confidently match this module. Your job is to
investigate and either find the correct Contrast application or confirm no match exists.

MODULE INFORMATION:
- Name: {module_name}
- Path: {module_path}
- Ecosystem: {ecosystem}
- Manifest: {manifest}
{contrast_app_name_line}
DETERMINISTIC SCORING CONTEXT:
{scoring_context}
{already_matched_context}

STEPS — follow in order, stop as soon as you have a match:

1. REVIEW CONTEXT: Look at the module info and top candidates above. The scorer uses
   token overlap (Jaccard similarity) + language alignment. If a candidate looks plausible
   despite a low score, note why.

2. READ MODULE FILES: Read key files in the module directory ({module_path}) for clues:
   - README, contrast_security.yaml, main source files, build configs
   - Look for application names, service names, deployment names

3. SEARCH CONTRAST: Try alternative search terms based on what you found:
   - Abbreviations, acronyms, deployment names, service names
   - Try at most 2-3 searches

4. RETURN RESULT:
   - If you found a match: return it with HIGH/MEDIUM/LOW confidence and reasoning
   - If no match exists: return application_id="NOT_FOUND", application_name="NOT_FOUND",
     confidence="LOW", and explain why no match was found

IMPORTANT: Do NOT dismiss a candidate just because its language differs from this module's
ecosystem. In monorepos, a frontend (e.g. Node) and backend (e.g. Java) often share the
same Contrast application. If a candidate's name matches and it's in the same repository,
language mismatch alone is not a reason to reject it.

COST DISCIPLINE: Each tool call costs tokens. Stop investigating as soon as you have
enough evidence to decide — do not exhaustively explore if a match is already clear.

DO NOT:
- Read more than 3 files total
- Make more than 2 Contrast search calls
- Explore unrelated directories outside the module path
"""


def _build_scoring_context(
    module: DiscoveredModule,
    candidates: list[AppCandidate],
    scores: list[tuple[AppCandidate, float]],
) -> str:
    """Build a summary of what the deterministic scorer found."""
    if not scores:
        return "No candidates scored above 0.0. The module name may be very different from any Contrast app name."

    lines = ["Top candidates from deterministic scoring:"]
    for candidate, score in scores[:TOP_N_CANDIDATES]:
        lines.append(
            f"  - {candidate.name} (id={candidate.app_id}, lang={candidate.language}) "
            f"→ score={score:.2f}"
        )

    if scores[0][1] < 0.3:
        lines.append("All scores are very low — names have little token overlap.")
    elif scores[0][1] < 0.5:
        lines.append("Best score is below the 0.5 threshold — close but not confident enough.")

    return "\n".join(lines)


def _score_all_candidates(
    module: DiscoveredModule,
    candidates: list[AppCandidate],
) -> list[tuple[AppCandidate, float]]:
    """Score all candidates and return sorted (desc) list of (candidate, score).

    Reuses resolver scoring functions but returns ALL scores (not just the best match)
    so the LLM agent can see what the deterministic scorer considered.
    """
    from ..resolver import extract_search_term, score_candidate

    search_term = extract_search_term(module)
    scored = [
        (c, score_candidate(module, c, search_term))
        for c in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def resolve_module(
    module: DiscoveredModule,
    candidates: list[AppCandidate],
    llm_config: LLMConfig,
    contrast_config: ContrastConfig,
    repo_path: str,
    jar_path: str | None = None,
    already_matched: dict[str, AppMatch] | None = None,
) -> Optional[LLMMatch]:
    """Run the LLM agent to resolve a single unmatched module.

    Returns:
        LLMMatch if the agent found a match, None if NOT_FOUND.
    """
    # Build context
    scores = _score_all_candidates(module, candidates)
    scoring_context = _build_scoring_context(module, candidates, scores)

    contrast_app_name_line = ""
    if module.contrast_app_name:
        contrast_app_name_line = f"- Contrast config app name: {module.contrast_app_name}\n"

    already_matched_context = ""
    if already_matched:
        lines = ["OTHER MODULES IN THIS REPO ALREADY MATCHED:"]
        for path, match in already_matched.items():
            lines.append(f"  - {path} → {match.app_name} (id={match.app_id})")
        lines.append("Consider whether this module might belong to the same application.")
        already_matched_context = "\n".join(lines)

    instructions = AGENT_INSTRUCTIONS.format(
        module_name=module.name,
        module_path=module.path,
        ecosystem=module.ecosystem.value,
        manifest=module.manifest.value,
        contrast_app_name_line=contrast_app_name_line,
        scoring_context=scoring_context,
        already_matched_context=already_matched_context,
    )

    # Create model and toolsets
    model = get_model(llm_config)
    toolsets = await create_mcp_toolsets(contrast_config, repo_path, jar_path)

    agent = Agent(
        model=model,
        output_type=LLMMatch,
        system_prompt=instructions,
        toolsets=toolsets,
        retries=2,
        history_processors=[_trim_messages],
    )

    log.info("LLM fallback for module: %s (%s)", module.name, module.path)

    t0 = time.monotonic()
    try:
        result = await agent.run(
            user_prompt=(
                f"Resolve the module '{module.name}' at path '{module.path}' "
                f"to a Contrast Security application. Use the tools available "
                f"to investigate and find the best match."
            ),
            usage_limits=UsageLimits(
                request_limit=MAX_MODEL_REQUESTS,
                tool_calls_limit=MAX_TOOL_CALLS,
            ),
        )

        elapsed = time.monotonic() - t0
        log.info("LLM usage for %s: %s (%.1fs)", module.name, result.usage(), elapsed)

        match = result.output

        # NOT_FOUND means the agent confirmed no match
        if match.application_id == "NOT_FOUND":
            log.info("LLM confirmed no match for: %s — %s", module.name, match.reasoning)
            return None

        log.info(
            "LLM matched %s → %s (%s confidence)",
            module.name, match.application_name, match.confidence,
        )
        return match

    except Exception as e:
        elapsed = time.monotonic() - t0
        log.error("LLM agent failed for %s (%.1fs): %s", module.name, elapsed, e)
        import traceback
        log.error(traceback.format_exc())
        return None


async def resolve_modules(
    modules: list[DiscoveredModule],
    candidates: list[AppCandidate],
    llm_config: LLMConfig,
    contrast_config: ContrastConfig,
    repo_path: str,
    jar_path: str | None = None,
    already_matched: dict[str, AppMatch] | None = None,
) -> dict[str, Optional[LLMMatch]]:
    """Run the LLM agent on a batch of unmatched modules.

    Returns {module.path: LLMMatch or None} for each module.
    """
    results = {}
    for module in modules:
        results[module.path] = await resolve_module(
            module=module,
            candidates=candidates,
            llm_config=llm_config,
            contrast_config=contrast_config,
            repo_path=repo_path,
            jar_path=jar_path,
            already_matched=already_matched,
        )
    return results
