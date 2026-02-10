"""Tests for module_identifier scanner."""

import json
from pathlib import Path

import pytest

from module_identifier.models import Ecosystem, Manifest
from module_identifier.scanner import (
    SKIP_DIRS,
    discover_modules,
    _extract_name,
    _name_from_package_json,
    _name_from_pom_xml,
    _name_from_go_mod,
    _name_from_composer_json,
    _name_from_pyproject_toml,
    _name_from_gradle,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo root."""
    return tmp_path


# --- Name extraction tests ---


class TestNameFromPackageJson:
    def test_extracts_name(self, tmp_repo):
        pkg = tmp_repo / "package.json"
        pkg.write_text(json.dumps({"name": "my-service", "version": "1.0.0"}))
        assert _name_from_package_json(pkg) == "my-service"

    def test_scoped_name(self, tmp_repo):
        pkg = tmp_repo / "package.json"
        pkg.write_text(json.dumps({"name": "@contrast/agent"}))
        assert _name_from_package_json(pkg) == "@contrast/agent"

    def test_missing_name(self, tmp_repo):
        pkg = tmp_repo / "package.json"
        pkg.write_text(json.dumps({"version": "1.0.0"}))
        assert _name_from_package_json(pkg) is None

    def test_empty_name(self, tmp_repo):
        pkg = tmp_repo / "package.json"
        pkg.write_text(json.dumps({"name": ""}))
        assert _name_from_package_json(pkg) is None


class TestNameFromPomXml:
    def test_group_and_artifact(self, tmp_repo):
        pom = tmp_repo / "pom.xml"
        pom.write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <groupId>com.example</groupId>
    <artifactId>my-app</artifactId>
</project>""")
        assert _name_from_pom_xml(pom) == "com.example:my-app"

    def test_artifact_only(self, tmp_repo):
        pom = tmp_repo / "pom.xml"
        pom.write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <artifactId>my-app</artifactId>
</project>""")
        assert _name_from_pom_xml(pom) == "my-app"

    def test_no_namespace(self, tmp_repo):
        pom = tmp_repo / "pom.xml"
        pom.write_text("""<?xml version="1.0"?>
<project>
    <groupId>com.example</groupId>
    <artifactId>my-app</artifactId>
</project>""")
        assert _name_from_pom_xml(pom) == "com.example:my-app"

    def test_no_artifact_id(self, tmp_repo):
        pom = tmp_repo / "pom.xml"
        pom.write_text("""<?xml version="1.0"?>
<project><groupId>com.example</groupId></project>""")
        assert _name_from_pom_xml(pom) is None


class TestNameFromGoMod:
    def test_extracts_module(self, tmp_repo):
        mod = tmp_repo / "go.mod"
        mod.write_text("module github.com/org/repo\n\ngo 1.21\n")
        assert _name_from_go_mod(mod) == "github.com/org/repo"

    def test_empty_file(self, tmp_repo):
        mod = tmp_repo / "go.mod"
        mod.write_text("")
        assert _name_from_go_mod(mod) is None


class TestNameFromComposerJson:
    def test_extracts_name(self, tmp_repo):
        composer = tmp_repo / "composer.json"
        composer.write_text(json.dumps({"name": "vendor/package"}))
        assert _name_from_composer_json(composer) == "vendor/package"

    def test_missing_name(self, tmp_repo):
        composer = tmp_repo / "composer.json"
        composer.write_text(json.dumps({"require": {}}))
        assert _name_from_composer_json(composer) is None


class TestNameFromPyprojectToml:
    def test_extracts_name(self, tmp_repo):
        toml = tmp_repo / "pyproject.toml"
        toml.write_text('[project]\nname = "my-package"\n')
        assert _name_from_pyproject_toml(toml) == "my-package"

    def test_missing_project(self, tmp_repo):
        toml = tmp_repo / "pyproject.toml"
        toml.write_text("[tool.pytest]\n")
        assert _name_from_pyproject_toml(toml) is None


class TestNameFromGradle:
    def test_kotlin_dsl(self, tmp_repo):
        settings = tmp_repo / "settings.gradle.kts"
        settings.write_text('rootProject.name = "my-service"\n')
        assert _name_from_gradle(tmp_repo) == "my-service"

    def test_groovy_dsl(self, tmp_repo):
        settings = tmp_repo / "settings.gradle"
        settings.write_text("rootProject.name = 'my-service'\n")
        assert _name_from_gradle(tmp_repo) == "my-service"

    def test_no_settings(self, tmp_repo):
        assert _name_from_gradle(tmp_repo) is None


# --- Scanner tests ---


class TestSkipDirs:
    def test_node_modules_skipped(self):
        assert "node_modules" in SKIP_DIRS

    def test_test_dirs_skipped(self):
        assert "test" in SKIP_DIRS
        assert "tests" in SKIP_DIRS

    def test_build_output_skipped(self):
        for d in ["dist", "build", "target", "out", "bin", "obj"]:
            assert d in SKIP_DIRS


class TestDiscoverModules:
    def test_single_node_module(self, tmp_repo):
        (tmp_repo / "package.json").write_text(json.dumps({"name": "my-app"}))
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "my-app"
        assert modules[0].ecosystem == Ecosystem.NODE
        assert modules[0].manifest == Manifest.PACKAGE_JSON
        assert modules[0].path == "."

    def test_single_maven_module(self, tmp_repo):
        (tmp_repo / "pom.xml").write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <groupId>com.example</groupId>
    <artifactId>my-app</artifactId>
</project>""")
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "com.example:my-app"

    def test_single_go_module(self, tmp_repo):
        (tmp_repo / "go.mod").write_text("module github.com/org/repo\n\ngo 1.21\n")
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "github.com/org/repo"

    def test_single_python_module(self, tmp_repo):
        (tmp_repo / "pyproject.toml").write_text('[project]\nname = "my-pkg"\n')
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "my-pkg"

    def test_single_ruby_module(self, tmp_repo):
        (tmp_repo / "Gemfile").write_text('source "https://rubygems.org"\n')
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == tmp_repo.name
        assert modules[0].ecosystem == Ecosystem.RUBY

    def test_single_php_module(self, tmp_repo):
        (tmp_repo / "composer.json").write_text(json.dumps({"name": "vendor/pkg"}))
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "vendor/pkg"

    def test_single_dotnet_module(self, tmp_repo):
        (tmp_repo / "packages.config").write_text("<packages></packages>")
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == tmp_repo.name
        assert modules[0].ecosystem == Ecosystem.DOTNET

    def test_empty_repo(self, tmp_repo):
        modules = discover_modules(tmp_repo)
        assert modules == []

    def test_skips_node_modules(self, tmp_repo):
        nm = tmp_repo / "node_modules" / "some-dep"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(json.dumps({"name": "some-dep"}))
        modules = discover_modules(tmp_repo)
        assert modules == []

    def test_skips_test_dirs(self, tmp_repo):
        test_dir = tmp_repo / "test" / "fixtures-app"
        test_dir.mkdir(parents=True)
        (test_dir / "package.json").write_text(json.dumps({"name": "fixture"}))
        modules = discover_modules(tmp_repo)
        assert modules == []

    def test_respects_depth_limit(self, tmp_repo):
        # Create a deeply nested module beyond depth 4
        deep = tmp_repo / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "package.json").write_text(json.dumps({"name": "deep"}))
        modules = discover_modules(tmp_repo, depth=4)
        assert not any(m.name == "deep" for m in modules)

    def test_finds_within_depth(self, tmp_repo):
        nested = tmp_repo / "services" / "api"
        nested.mkdir(parents=True)
        (nested / "package.json").write_text(json.dumps({"name": "api"}))
        modules = discover_modules(tmp_repo, depth=4)
        assert len(modules) == 1
        assert modules[0].name == "api"
        assert modules[0].path == "services/api"

    def test_multiple_ecosystems_same_dir(self, tmp_repo):
        (tmp_repo / "package.json").write_text(json.dumps({"name": "frontend"}))
        (tmp_repo / "packages.config").write_text("<packages></packages>")
        modules = discover_modules(tmp_repo)
        assert len(modules) == 2
        ecosystems = {m.ecosystem for m in modules}
        assert ecosystems == {Ecosystem.NODE, Ecosystem.DOTNET}

    def test_directory_name_fallback(self, tmp_repo):
        (tmp_repo / "requirements.txt").write_text("flask\n")
        modules = discover_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == tmp_repo.name

    def test_prefers_primary_manifest(self, tmp_repo):
        # package.json should win over yarn.lock for Node
        (tmp_repo / "package.json").write_text(json.dumps({"name": "from-pkg"}))
        (tmp_repo / "yarn.lock").write_text("")
        modules = discover_modules(tmp_repo)
        node_modules = [m for m in modules if m.ecosystem == Ecosystem.NODE]
        assert len(node_modules) == 1
        assert node_modules[0].manifest == Manifest.PACKAGE_JSON
