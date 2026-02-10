"""Resolve discovered modules to Contrast application IDs.

Flow: extract search term → search Contrast → score candidates → pick best match.
"""

import re
from dataclasses import dataclass
from typing import Optional

from .models import DiscoveredModule, Ecosystem


@dataclass
class AppCandidate:
    """An application returned from Contrast search."""
    app_id: str
    name: str
    language: str


@dataclass
class AppMatch:
    """A resolved match between a discovered module and a Contrast application."""
    module: DiscoveredModule
    app_id: str
    app_name: str
    confidence: float  # 0.0 - 1.0
    search_term: str


# -- Search term extraction --

def extract_search_term(module: DiscoveredModule) -> str:
    """Extract a clean search term from a module name.

    If the module has a contrast_app_name (from contrast_security.yaml),
    that takes priority — it's the Contrast identity.

    Otherwise strips ecosystem-specific prefixes/structure to get the most
    searchable short name:
      - Maven:  "com.acme:order-api"         → "order-api"
      - Node:   "@scope/billing-api"          → "billing-api"
      - Go:     "github.com/acme/inv-service" → "inv-service"
      - PHP:    "vendor/package"              → "package"
      - Others: returned as-is
    """
    if module.contrast_app_name:
        return module.contrast_app_name

    name = module.name

    # Maven — groupId:artifactId → artifactId
    if ":" in name and module.ecosystem == Ecosystem.JAVA:
        return name.split(":")[-1]

    # Node scoped — @scope/name → name
    if name.startswith("@") and "/" in name:
        return name.split("/", 1)[-1]

    # Go module path — github.com/org/repo → repo
    if "/" in name and module.ecosystem == Ecosystem.GO:
        return name.rsplit("/", 1)[-1]

    # PHP — vendor/package → package
    if "/" in name and module.ecosystem == Ecosystem.PHP:
        return name.rsplit("/", 1)[-1]

    return name


# -- Candidate scoring --

_ECOSYSTEM_TO_LANGUAGE: dict[Ecosystem, str] = {
    Ecosystem.JAVA: "Java",
    Ecosystem.NODE: "Node",
    Ecosystem.PYTHON: "Python",
    Ecosystem.GO: "Go",
    Ecosystem.RUBY: "Ruby",
    Ecosystem.DOTNET: ".NET Core",
    Ecosystem.PHP: "PHP",
}


def _tokenize(name: str) -> set[str]:
    """Split a name into lowercase tokens on common separators."""
    return set(re.split(r"[-_.\s]+", name.lower())) - {""}


def score_candidate(
    module: DiscoveredModule,
    candidate: AppCandidate,
    search_term: str,
) -> float:
    """Score how well a Contrast app candidate matches a discovered module.

    Scoring factors:
      - Exact name match (search term == app name): 0.8 base
      - Token overlap (Jaccard similarity): 0.0 - 0.7
      - Language alignment bonus: +0.2

    Max score is 1.0 (exact name + correct language).
    """
    app_name_lower = candidate.name.lower()
    term_lower = search_term.lower()
    expected_lang = _ECOSYSTEM_TO_LANGUAGE.get(module.ecosystem)
    lang_match = expected_lang and candidate.language == expected_lang

    # Exact name match
    if app_name_lower == term_lower:
        return 1.0 if lang_match else 0.8

    # Token-based similarity (Jaccard)
    module_tokens = _tokenize(search_term)
    app_tokens = _tokenize(candidate.name)

    if not module_tokens or not app_tokens:
        return 0.0

    intersection = module_tokens & app_tokens
    union = module_tokens | app_tokens
    jaccard = len(intersection) / len(union)

    score = jaccard * 0.7

    # Language alignment bonus
    if lang_match:
        score += 0.2

    return min(score, 1.0)


# -- Resolver --


def resolve_module(
    module: DiscoveredModule,
    candidates: list[AppCandidate],
    confidence_threshold: float = 0.5,
) -> Optional[AppMatch]:
    """Resolve a single module to a Contrast app ID.

    Scores the module against a pre-fetched list of all org apps.
    Returns None if no candidate meets the confidence threshold.
    """
    search_term = extract_search_term(module)

    if not candidates:
        return None

    best_candidate = None
    best_score = 0.0

    for candidate in candidates:
        score = score_candidate(module, candidate, search_term)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_candidate is None or best_score < confidence_threshold:
        return None

    return AppMatch(
        module=module,
        app_id=best_candidate.app_id,
        app_name=best_candidate.name,
        confidence=best_score,
        search_term=search_term,
    )


def resolve_modules(
    modules: list[DiscoveredModule],
    candidates: list[AppCandidate],
    confidence_threshold: float = 0.5,
) -> dict[str, Optional[AppMatch]]:
    """Resolve a list of discovered modules to Contrast app IDs.

    Scores each module against the same pre-fetched candidate list.
    Returns {module.path: AppMatch or None} for every module.
    """
    return {
        module.path: resolve_module(module, candidates, confidence_threshold)
        for module in modules
    }
