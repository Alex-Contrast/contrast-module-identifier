"""Tests for module_identifier resolver (search term extraction, scoring, resolution)."""

from module_identifier.models import DiscoveredModule, Ecosystem, Manifest
from module_identifier.resolver import (
    AppCandidate,
    AppMatch,
    extract_search_term,
    score_candidate,
    resolve_module,
    resolve_modules,
    _tokenize,
)


def _module(name: str, manifest: Manifest, ecosystem: Ecosystem, path: str = ".") -> DiscoveredModule:
    return DiscoveredModule(name=name, path=path, manifest=manifest, ecosystem=ecosystem)


# --- Search term extraction ---


class TestExtractSearchTerm:
    def test_maven_group_artifact(self):
        m = _module("com.acme:order-api", Manifest.POM_XML, Ecosystem.JAVA)
        assert extract_search_term(m) == "order-api"

    def test_maven_artifact_only(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        assert extract_search_term(m) == "order-api"

    def test_node_scoped(self):
        m = _module("@acme/billing-api", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        assert extract_search_term(m) == "billing-api"

    def test_node_unscoped(self):
        m = _module("my-app", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        assert extract_search_term(m) == "my-app"

    def test_go_module_path(self):
        m = _module("github.com/acme/inventory-service", Manifest.GO_MOD, Ecosystem.GO)
        assert extract_search_term(m) == "inventory-service"

    def test_php_vendor_package(self):
        m = _module("vendor/payment-gateway", Manifest.COMPOSER_JSON, Ecosystem.PHP)
        assert extract_search_term(m) == "payment-gateway"

    def test_python_passthrough(self):
        m = _module("data-pipeline", Manifest.PYPROJECT_TOML, Ecosystem.PYTHON)
        assert extract_search_term(m) == "data-pipeline"

    def test_ruby_passthrough(self):
        m = _module("my-app", Manifest.GEMFILE, Ecosystem.RUBY)
        assert extract_search_term(m) == "my-app"

    def test_dirname_fallback_passthrough(self):
        m = _module("src", Manifest.REQUIREMENTS_TXT, Ecosystem.PYTHON)
        assert extract_search_term(m) == "src"

    def test_dotnet_passthrough(self):
        m = _module("MyApp", Manifest.PACKAGES_CONFIG, Ecosystem.DOTNET)
        assert extract_search_term(m) == "MyApp"

    def test_contrast_app_name_takes_priority(self):
        m = DiscoveredModule(
            name="com.example:employee-management",
            path=".",
            manifest=Manifest.POM_XML,
            ecosystem=Ecosystem.JAVA,
            contrast_app_name="alex-employee-management",
        )
        assert extract_search_term(m) == "alex-employee-management"

    def test_contrast_app_name_none_falls_through(self):
        m = DiscoveredModule(
            name="com.example:employee-management",
            path=".",
            manifest=Manifest.POM_XML,
            ecosystem=Ecosystem.JAVA,
            contrast_app_name=None,
        )
        assert extract_search_term(m) == "employee-management"


# --- Tokenization ---


class TestTokenize:
    def test_hyphenated(self):
        assert _tokenize("order-api") == {"order", "api"}

    def test_underscored(self):
        assert _tokenize("order_api") == {"order", "api"}

    def test_dotted(self):
        assert _tokenize("com.acme.api") == {"com", "acme", "api"}

    def test_mixed(self):
        assert _tokenize("my-app_v2.0") == {"my", "app", "v2", "0"}

    def test_single_word(self):
        assert _tokenize("webgoat") == {"webgoat"}

    def test_empty(self):
        assert _tokenize("") == set()


# --- Scoring ---


class TestScoreCandidate:
    def test_exact_match_same_language(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        c = AppCandidate("id1", "order-api", "Java")
        assert score_candidate(m, c, "order-api") == 1.0

    def test_exact_match_different_language(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        c = AppCandidate("id1", "order-api", "Node")
        assert score_candidate(m, c, "order-api") == 0.8

    def test_exact_match_case_insensitive(self):
        m = _module("OrderApi", Manifest.POM_XML, Ecosystem.JAVA)
        c = AppCandidate("id1", "orderapi", "Java")
        assert score_candidate(m, c, "OrderApi") == 1.0

    def test_prefixed_name_same_language(self):
        """alex-employee-management vs employee-management."""
        m = _module("employee-management", Manifest.POM_XML, Ecosystem.JAVA)
        c = AppCandidate("id1", "alex-employee-management", "Java")
        # tokens: {employee, management} vs {alex, employee, management}
        # jaccard = 2/3, score = 2/3 * 0.7 + 0.2 = ~0.67
        score = score_candidate(m, c, "employee-management")
        assert 0.6 < score < 0.7

    def test_low_overlap(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        c = AppCandidate("id1", "api-gateway", "Java")
        # tokens: {order, api} vs {api, gateway} → jaccard = 1/3
        score = score_candidate(m, c, "order-api")
        assert score < 0.5

    def test_no_overlap(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        c = AppCandidate("id1", "webgoat-server", "Java")
        # No token overlap but same language → 0.2 from language bonus only
        assert score_candidate(m, c, "order-api") == 0.2

    def test_no_overlap_no_language(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        c = AppCandidate("id1", "webgoat-server", "Node")
        assert score_candidate(m, c, "order-api") == 0.0

    def test_language_bonus(self):
        """Same token overlap, different languages — language match scores higher."""
        m = _module("juice-shop", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        c_node = AppCandidate("id1", "my-juice-shop", "Node")
        c_java = AppCandidate("id2", "my-juice-shop", "Java")
        score_node = score_candidate(m, c_node, "juice-shop")
        score_java = score_candidate(m, c_java, "juice-shop")
        assert score_node > score_java


# --- resolve_module ---


class TestResolveModule:
    def test_exact_match(self):
        m = _module("webgoat-server", Manifest.POM_XML, Ecosystem.JAVA)
        apps = [AppCandidate("abc-123", "webgoat-server", "Java")]

        result = resolve_module(m, apps)
        assert result is not None
        assert result.app_id == "abc-123"
        assert result.app_name == "webgoat-server"
        assert result.confidence == 1.0
        assert result.search_term == "webgoat-server"

    def test_no_candidates(self):
        m = _module("nonexistent-app", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        assert resolve_module(m, []) is None

    def test_below_threshold(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        apps = [AppCandidate("id1", "completely-different", "Java")]
        assert resolve_module(m, apps) is None

    def test_picks_best_candidate(self):
        m = _module("employee-management", Manifest.POM_XML, Ecosystem.JAVA)
        apps = [
            AppCandidate("id1", "alex-employee-management", "Java"),
            AppCandidate("id2", "employee-management", "Java"),
            AppCandidate("id3", "jacob-employee-management", "Java"),
        ]

        result = resolve_module(m, apps)
        assert result is not None
        assert result.app_id == "id2"
        assert result.confidence == 1.0

    def test_prefers_correct_language(self):
        m = _module("juice-shop", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        apps = [
            AppCandidate("id1", "juice-shop", "Java"),
            AppCandidate("id2", "juice-shop", "Node"),
        ]

        result = resolve_module(m, apps)
        assert result is not None
        assert result.app_id == "id2"
        assert result.confidence == 1.0

    def test_maven_prefix_stripped(self):
        """com.acme:order-api should match against 'order-api'."""
        m = _module("com.acme:order-api", Manifest.POM_XML, Ecosystem.JAVA)
        apps = [AppCandidate("id1", "order-api", "Java")]

        result = resolve_module(m, apps)
        assert result is not None
        assert result.search_term == "order-api"
        assert result.confidence == 1.0

    def test_custom_threshold(self):
        m = _module("order-api", Manifest.POM_XML, Ecosystem.JAVA)
        apps = [AppCandidate("id1", "alex-order-api", "Java")]

        # Default threshold (0.5) — should match
        assert resolve_module(m, apps, confidence_threshold=0.5) is not None
        # High threshold — should not match
        assert resolve_module(m, apps, confidence_threshold=0.9) is None


# --- resolve_modules ---


class TestResolveModules:
    def test_maps_all_modules(self):
        modules = [
            _module("webgoat-server", Manifest.POM_XML, Ecosystem.JAVA, path="backend"),
            _module("juice-shop", Manifest.PACKAGE_JSON, Ecosystem.NODE, path="frontend"),
            _module("unknown-thing", Manifest.GEMFILE, Ecosystem.RUBY, path="scripts"),
        ]
        apps = [
            AppCandidate("id1", "webgoat-server", "Java"),
            AppCandidate("id2", "juice-shop", "Node"),
        ]

        result = resolve_modules(modules, apps)

        assert len(result) == 3
        assert result["backend"] is not None
        assert result["backend"].app_id == "id1"
        assert result["frontend"] is not None
        assert result["frontend"].app_id == "id2"
        assert result["scripts"] is None  # no match

    def test_empty_modules(self):
        result = resolve_modules([], [])
        assert result == {}


# --- Fork naming (AIML-475) ---


class TestForkNaming:
    """Forked repos keep upstream manifest names — scoring should still work."""

    def test_manifest_name_matches_despite_fork_dir(self):
        """Module name from pom.xml is 'employee-management' even in a fork dir."""
        # The module name comes from the manifest, not the repo/dir name.
        # A fork named 'employee-management-fork' still has artifactId=employee-management.
        m = _module("employee-management", Manifest.POM_XML, Ecosystem.JAVA, path="employee-management-fork")
        apps = [AppCandidate("id1", "employee-management", "Java")]

        result = resolve_module(m, apps)
        assert result is not None
        assert result.app_id == "id1"
        assert result.confidence == 1.0

    def test_node_fork_keeps_package_name(self):
        """Forked Node repo: package.json name unchanged, still matches."""
        m = _module("billing-api", Manifest.PACKAGE_JSON, Ecosystem.NODE, path="billing-api-fork")
        apps = [AppCandidate("id1", "billing-api", "Node")]

        result = resolve_module(m, apps)
        assert result is not None
        assert result.app_id == "id1"
        assert result.confidence == 1.0

    def test_contrast_yaml_matches_regardless_of_repo_name(self):
        """contrast_security.yaml overrides everything — fork dir name irrelevant."""
        m = DiscoveredModule(
            name="com.example:employee-management",
            path="my-fork-of-employee-management",
            manifest=Manifest.POM_XML,
            ecosystem=Ecosystem.JAVA,
            contrast_app_name="alex-employee-management",
        )
        apps = [
            AppCandidate("id1", "employee-management", "Java"),
            AppCandidate("id2", "alex-employee-management", "Java"),
        ]

        result = resolve_module(m, apps)
        assert result is not None
        assert result.app_id == "id2"
        assert result.app_name == "alex-employee-management"
