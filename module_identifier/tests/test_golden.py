"""Golden dataset tests: resolve known modules against real org app list."""

import json
from pathlib import Path

import pytest

from module_identifier.models import DiscoveredModule, Ecosystem, Manifest
from module_identifier.resolver import AppCandidate, resolve_module, resolve_modules


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def golden_apps() -> list[AppCandidate]:
    """Load the real org app list captured from Contrast."""
    with open(FIXTURES / "golden_apps.json") as f:
        data = json.load(f)
    return [AppCandidate(**app) for app in data]


def _module(
    name: str,
    manifest: Manifest,
    ecosystem: Ecosystem,
    path: str = ".",
    contrast_app_name: str | None = None,
) -> DiscoveredModule:
    return DiscoveredModule(
        name=name, path=path, manifest=manifest,
        ecosystem=ecosystem, contrast_app_name=contrast_app_name,
    )


# --- Known correct mappings per ecosystem ---


class TestGoldenJava:
    def test_exact_match(self, golden_apps):
        m = _module("webgoat-sm", Manifest.POM_XML, Ecosystem.JAVA)
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert result.app_name == "webgoat-sm"
        assert result.confidence == 1.0

    def test_partial_match(self, golden_apps):
        """webgoat-wiz-demo should match against webgoat-wiz-demo."""
        m = _module("com.example:webgoat-wiz-demo", Manifest.POM_XML, Ecosystem.JAVA)
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert result.app_name == "webgoat-wiz-demo"
        assert result.search_term == "webgoat-wiz-demo"


class TestGoldenNode:
    def test_exact_match(self, golden_apps):
        m = _module("demo-app", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert result.app_name == "demo-app"

    def test_scoped_name(self, golden_apps):
        m = _module("@scope/node", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert result.app_name == "node"
        assert result.search_term == "node"


class TestGoldenPython:
    def test_cargo_cats_docservice(self, golden_apps):
        m = _module(
            "contrast-cargo-cats-docservice",
            Manifest.PYPROJECT_TOML,
            Ecosystem.PYTHON,
        )
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert "docservice" in result.app_name


class TestGoldenGo:
    def test_go_module_path(self, golden_apps):
        m = _module(
            "github.com/contrast/max-assess-app",
            Manifest.GO_MOD,
            Ecosystem.GO,
        )
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert result.app_name == "max-assess-app"
        assert result.search_term == "max-assess-app"


class TestGoldenDotnet:
    def test_imageservice(self, golden_apps):
        m = _module(
            "contrast-cargo-cats-imageservice",
            Manifest.PACKAGES_CONFIG,
            Ecosystem.DOTNET,
        )
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert "imageservice" in result.app_name


class TestGoldenPHP:
    def test_reportservice(self, golden_apps):
        m = _module(
            "contrast/contrast-cargo-cats-reportservice",
            Manifest.COMPOSER_JSON,
            Ecosystem.PHP,
        )
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert "reportservice" in result.app_name
        assert result.search_term == "contrast-cargo-cats-reportservice"


# --- contrast_security.yaml override ---


class TestGoldenYamlOverride:
    def test_yaml_corrects_match(self, golden_apps):
        """Without yaml, would match generic name. With yaml, matches specific."""
        m = _module(
            "com.example:webgoat",
            Manifest.POM_XML,
            Ecosystem.JAVA,
            contrast_app_name="webgoat-sm",
        )
        result = resolve_module(m, golden_apps)
        assert result is not None
        assert result.app_name == "webgoat-sm"
        assert result.search_term == "webgoat-sm"
        assert result.confidence == 1.0


# --- Known non-matches ---


class TestGoldenNoMatch:
    def test_unknown_module(self, golden_apps):
        m = _module("my-internal-tool", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        assert resolve_module(m, golden_apps) is None

    def test_teamserver_submodule(self, golden_apps):
        m = _module("teamserver-app", Manifest.POM_XML, Ecosystem.JAVA)
        assert resolve_module(m, golden_apps) is None

    def test_utility_script(self, golden_apps):
        m = _module("squid_proxy", Manifest.PACKAGE_JSON, Ecosystem.NODE)
        assert resolve_module(m, golden_apps) is None


# --- Batch resolution ---


class TestGoldenBatch:
    def test_mixed_repo(self, golden_apps):
        modules = [
            _module("webgoat-sm", Manifest.POM_XML, Ecosystem.JAVA, path="backend"),
            _module("demo-app", Manifest.PACKAGE_JSON, Ecosystem.NODE, path="frontend"),
            _module("my-internal-tool", Manifest.PYPROJECT_TOML, Ecosystem.PYTHON, path="scripts"),
        ]
        results = resolve_modules(modules, golden_apps)

        assert results["backend"] is not None
        assert results["backend"].app_name == "webgoat-sm"
        assert results["frontend"] is not None
        assert results["frontend"].app_name == "demo-app"
        assert results["scripts"] is None
