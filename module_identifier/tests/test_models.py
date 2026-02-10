"""Tests for module_identifier models."""

from module_identifier.models import DiscoveredModule, Ecosystem, Manifest


class TestManifest:
    def test_ecosystem_mapping(self):
        assert Manifest.POM_XML.ecosystem == Ecosystem.JAVA
        assert Manifest.PACKAGE_JSON.ecosystem == Ecosystem.NODE
        assert Manifest.PYPROJECT_TOML.ecosystem == Ecosystem.PYTHON
        assert Manifest.GO_MOD.ecosystem == Ecosystem.GO
        assert Manifest.GEMFILE.ecosystem == Ecosystem.RUBY
        assert Manifest.PACKAGES_CONFIG.ecosystem == Ecosystem.DOTNET
        assert Manifest.COMPOSER_JSON.ecosystem == Ecosystem.PHP

    def test_all_manifests_have_ecosystem(self):
        for manifest in Manifest:
            assert manifest.ecosystem in Ecosystem

    def test_gradle_variants(self):
        assert Manifest.BUILD_GRADLE.ecosystem == Ecosystem.JAVA
        assert Manifest.BUILD_GRADLE_KTS.ecosystem == Ecosystem.JAVA
        assert Manifest.SETTINGS_GRADLE.ecosystem == Ecosystem.JAVA
        assert Manifest.SETTINGS_GRADLE_KTS.ecosystem == Ecosystem.JAVA


class TestDiscoveredModule:
    def test_creation(self):
        m = DiscoveredModule(
            name="my-app",
            path=".",
            manifest=Manifest.PACKAGE_JSON,
            ecosystem=Ecosystem.NODE,
        )
        assert m.name == "my-app"
        assert m.path == "."
        assert m.manifest == Manifest.PACKAGE_JSON
        assert m.ecosystem == Ecosystem.NODE

    def test_serialization(self):
        m = DiscoveredModule(
            name="my-app",
            path="services/api",
            manifest=Manifest.POM_XML,
            ecosystem=Ecosystem.JAVA,
        )
        data = m.model_dump()
        assert data["name"] == "my-app"
        assert data["manifest"] == "pom.xml"
        assert data["ecosystem"] == "java"

    def test_json_roundtrip(self):
        m = DiscoveredModule(
            name="my-app",
            path=".",
            manifest=Manifest.GO_MOD,
            ecosystem=Ecosystem.GO,
        )
        json_str = m.model_dump_json()
        restored = DiscoveredModule.model_validate_json(json_str)
        assert restored == m
