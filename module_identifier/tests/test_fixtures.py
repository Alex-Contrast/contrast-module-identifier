"""Fixture-based tests for module_identifier discovery pipeline.

Each fixture is a realistic directory structure that validates the full
discover_modules pipeline. Fixtures are grouped into categories:

1. Single ecosystem — one manifest, deterministic name extraction
2. LLM fallback — cases where deterministic naming fails (dirname fallback)
3. Monorepo — multi-module structures, both clean and messy
4. Lock-file-only — lock files without primary manifests (invisible to scanner)
5. No name parser — manifests we detect but can't extract names from
6. Malformed — corrupt manifest files
"""

from pathlib import Path

import pytest

from module_identifier import discover_modules
from module_identifier.models import Ecosystem, Manifest


FIXTURES = Path(__file__).parent / "fixtures"


def _modules_dict(fixture_name: str) -> dict[str, dict]:
    """Run discovery on a fixture and return {path: module_data} for easy assertions."""
    modules = discover_modules(FIXTURES / fixture_name)
    return {
        m.path: {"name": m.name, "manifest": m.manifest, "ecosystem": m.ecosystem}
        for m in modules
    }


# --- Single ecosystem: deterministic name extraction ---


class TestSingleEcosystem:
    def test_java(self):
        result = _modules_dict("java")
        assert len(result) == 1
        assert result["."]["name"] == "com.example:user-service"
        assert result["."]["manifest"] == Manifest.POM_XML
        assert result["."]["ecosystem"] == Ecosystem.JAVA

    def test_node(self):
        result = _modules_dict("node")
        assert len(result) == 1
        assert result["."]["name"] == "@acme/billing-api"
        assert result["."]["manifest"] == Manifest.PACKAGE_JSON
        assert result["."]["ecosystem"] == Ecosystem.NODE

    def test_python(self):
        result = _modules_dict("python")
        assert len(result) == 1
        assert result["."]["name"] == "data-pipeline"
        assert result["."]["manifest"] == Manifest.PYPROJECT_TOML
        assert result["."]["ecosystem"] == Ecosystem.PYTHON

    def test_go(self):
        result = _modules_dict("go")
        assert len(result) == 1
        assert result["."]["name"] == "github.com/acme/inventory-service"
        assert result["."]["manifest"] == Manifest.GO_MOD
        assert result["."]["ecosystem"] == Ecosystem.GO

    def test_ruby_dirname_fallback(self):
        result = _modules_dict("ruby")
        assert len(result) == 1
        # Ruby has no name in Gemfile — falls back to directory name
        assert result["."]["name"] == "ruby"
        assert result["."]["manifest"] == Manifest.GEMFILE
        assert result["."]["ecosystem"] == Ecosystem.RUBY

    def test_dotnet_dirname_fallback(self):
        result = _modules_dict("dotnet")
        assert len(result) == 1
        # .NET packages.config has no name — falls back to directory name
        assert result["."]["name"] == "dotnet"
        assert result["."]["manifest"] == Manifest.PACKAGES_CONFIG
        assert result["."]["ecosystem"] == Ecosystem.DOTNET

    def test_php(self):
        result = _modules_dict("php")
        assert len(result) == 1
        assert result["."]["name"] == "acme/payment-gateway"
        assert result["."]["manifest"] == Manifest.COMPOSER_JSON
        assert result["."]["ecosystem"] == Ecosystem.PHP


# --- LLM fallback: deterministic finds the module but name is garbage ---


class TestLlmFallbackCases:
    def test_generic_dirname_src(self):
        """requirements.txt in src/ produces name='src' — LLM should improve this."""
        result = _modules_dict("fallback-generic-dirname")
        assert "src" in result
        # Deterministic gives us "src" which is useless
        assert result["src"]["name"] == "src"
        assert result["src"]["ecosystem"] == Ecosystem.PYTHON

    def test_generic_dirname_app(self):
        """Gemfile in app/ produces name='app' — LLM should improve this."""
        result = _modules_dict("fallback-generic-dirname")
        assert "app" in result
        assert result["app"]["name"] == "app"
        assert result["app"]["ecosystem"] == Ecosystem.RUBY

    def test_no_manifest_name(self):
        """package.json without a name field falls back to directory name."""
        result = _modules_dict("fallback-no-manifest-name")
        assert len(result) == 1
        assert result["."]["name"] == "fallback-no-manifest-name"
        assert result["."]["manifest"] == Manifest.PACKAGE_JSON
        assert result["."]["ecosystem"] == Ecosystem.NODE

    def test_ambiguous_multi_ecosystem(self):
        """Three ecosystems in one dir — Node has a real name, others are dirname fallbacks."""
        modules = discover_modules(FIXTURES / "fallback-ambiguous")
        assert len(modules) == 3
        by_eco = {m.ecosystem: m for m in modules}
        # Node has a real name from package.json
        assert by_eco[Ecosystem.NODE].name == "frontend-build"
        # Python and Ruby fall back to dirname
        assert by_eco[Ecosystem.PYTHON].name == "fallback-ambiguous"
        assert by_eco[Ecosystem.RUBY].name == "fallback-ambiguous"


# --- Lock-file-only: lock files without primary manifests ---


class TestLockFileOnly:
    """Lock files (yarn.lock, Gemfile.lock, poetry.lock, Gopkg.lock) are low-priority
    in _PRIMARY_MANIFESTS. When no primary manifest exists, lock files still detect
    the module — but names are always dirname fallback."""

    def test_yarn_lock_detected(self):
        result = _modules_dict("fallback-lock-file-only")
        assert result["node-app"]["name"] == "node-app"
        assert result["node-app"]["manifest"] == Manifest.YARN_LOCK
        assert result["node-app"]["ecosystem"] == Ecosystem.NODE

    def test_gemfile_lock_detected(self):
        result = _modules_dict("fallback-lock-file-only")
        assert result["ruby-app"]["name"] == "ruby-app"
        assert result["ruby-app"]["manifest"] == Manifest.GEMFILE_LOCK
        assert result["ruby-app"]["ecosystem"] == Ecosystem.RUBY

    def test_poetry_lock_detected(self):
        result = _modules_dict("fallback-lock-file-only")
        assert result["python-app"]["name"] == "python-app"
        assert result["python-app"]["manifest"] == Manifest.POETRY_LOCK
        assert result["python-app"]["ecosystem"] == Ecosystem.PYTHON

    def test_gopkg_lock_detected(self):
        result = _modules_dict("fallback-lock-file-only")
        assert result["go-app"]["name"] == "go-app"
        assert result["go-app"]["manifest"] == Manifest.GOPKG_LOCK
        assert result["go-app"]["ecosystem"] == Ecosystem.GO

    def test_all_detected(self):
        result = _modules_dict("fallback-lock-file-only")
        assert len(result) == 4


# --- No name parser: manifests we detect but can't extract names from ---


class TestNoNameParser:
    """These manifests are detected by the scanner but have no name extraction
    logic, so they always fall back to directory name."""

    def test_build_sbt_dirname_fallback(self):
        """build.sbt contains name := \"analytics-engine\" but we don't parse it."""
        result = _modules_dict("fallback-no-name-parser")
        assert result["scala-app"]["name"] == "scala-app"
        assert result["scala-app"]["manifest"] == Manifest.BUILD_SBT
        assert result["scala-app"]["ecosystem"] == Ecosystem.JAVA

    def test_gradle_without_settings_dirname_fallback(self):
        """build.gradle.kts without settings.gradle — no rootProject.name to extract."""
        result = _modules_dict("fallback-no-name-parser")
        assert result["gradle-app"]["name"] == "gradle-app"
        assert result["gradle-app"]["manifest"] == Manifest.BUILD_GRADLE_KTS
        assert result["gradle-app"]["ecosystem"] == Ecosystem.JAVA

    def test_pipfile_dirname_fallback(self):
        """Pipfile has no name field — always dirname."""
        result = _modules_dict("fallback-no-name-parser")
        assert result["python-app"]["name"] == "python-app"
        assert result["python-app"]["manifest"] == Manifest.PIPFILE
        assert result["python-app"]["ecosystem"] == Ecosystem.PYTHON


# --- Malformed: corrupt manifest files ---


class TestMalformedManifests:
    """When manifest files are corrupt or unparseable, the scanner still detects
    the module (the file exists) but name extraction fails gracefully and falls
    back to directory name."""

    def test_invalid_json(self):
        """Broken package.json — detected but name falls back to dirname."""
        result = _modules_dict("fallback-malformed")
        assert result["bad-json"]["name"] == "bad-json"
        assert result["bad-json"]["manifest"] == Manifest.PACKAGE_JSON

    def test_invalid_xml(self):
        """Broken pom.xml — detected but name falls back to dirname."""
        result = _modules_dict("fallback-malformed")
        assert result["bad-xml"]["name"] == "bad-xml"
        assert result["bad-xml"]["manifest"] == Manifest.POM_XML

    def test_invalid_toml(self):
        """Broken pyproject.toml — detected but name falls back to dirname."""
        result = _modules_dict("fallback-malformed")
        assert result["bad-toml"]["name"] == "bad-toml"
        assert result["bad-toml"]["manifest"] == Manifest.PYPROJECT_TOML


# --- Monorepo: multi-module structures ---


class TestMonorepoClean:
    def test_finds_all_declared_modules(self):
        result = _modules_dict("monorepo-clean")
        # 3 declared + root from scanner
        assert "services/api" in result
        assert "services/worker" in result
        assert "libs/common" in result

    def test_declared_modules_come_from_settings(self):
        result = _modules_dict("monorepo-clean")
        for path in ("services/api", "services/worker", "libs/common"):
            assert result[path]["manifest"] == Manifest.SETTINGS_GRADLE_KTS

    def test_declared_module_names(self):
        result = _modules_dict("monorepo-clean")
        assert result["services/api"]["name"] == "api"
        assert result["services/worker"]["name"] == "worker"
        assert result["libs/common"]["name"] == "common"

    def test_root_also_found(self):
        result = _modules_dict("monorepo-clean")
        assert "." in result
        assert result["."]["name"] == "platform"
        assert result["."]["ecosystem"] == Ecosystem.JAVA


class TestMonorepoNasty:
    def test_declared_java_modules_found(self):
        result = _modules_dict("monorepo-nasty")
        assert "services/order-api" in result
        assert result["services/order-api"]["name"] == "com.acme:order-api"
        assert "services/notification-worker" in result
        assert result["services/notification-worker"]["name"] == "com.acme:notification-worker"

    def test_test_dir_filtered(self):
        """test/integration-tests is declared in pom.xml but should be filtered."""
        result = _modules_dict("monorepo-nasty")
        assert "test/integration-tests" not in result

    def test_scanner_finds_undeclared_node(self):
        """frontend/ is not declared anywhere — scanner picks it up."""
        result = _modules_dict("monorepo-nasty")
        assert "frontend" in result
        assert result["frontend"]["name"] == "acme-dashboard"
        assert result["frontend"]["ecosystem"] == Ecosystem.NODE

    def test_scanner_finds_undeclared_python(self):
        """libs/shared-utils has a pyproject.toml — scanner picks it up."""
        result = _modules_dict("monorepo-nasty")
        assert "libs/shared-utils" in result
        assert result["libs/shared-utils"]["name"] == "acme-shared-utils"
        assert result["libs/shared-utils"]["ecosystem"] == Ecosystem.PYTHON

    def test_deploy_script_dirname_fallback(self):
        """scripts/deploy has requirements.txt — name is dirname fallback (LLM candidate)."""
        result = _modules_dict("monorepo-nasty")
        assert "scripts/deploy" in result
        assert result["scripts/deploy"]["name"] == "deploy"

    def test_deep_nested_still_found(self):
        """tools/codegen/templates/deep is at depth 4 — just within limit."""
        result = _modules_dict("monorepo-nasty")
        assert "tools/codegen/templates/deep" in result
        assert result["tools/codegen/templates/deep"]["name"] == "template-stub"

    def test_root_pom_found(self):
        result = _modules_dict("monorepo-nasty")
        assert "." in result
        assert result["."]["name"] == "com.acme:monolith"

    def test_total_module_count(self):
        """Should find 7 modules: root + 2 declared java + frontend + shared-utils + deploy + deep."""
        result = _modules_dict("monorepo-nasty")
        assert len(result) == 7


# --- Node: workspace and monorepo variants ---


class TestNodeWorkspacesGlob:
    """Workspaces declared with glob pattern (packages/*). Declarations find
    workspace packages, scanner catches packages outside the workspace glob."""

    def test_workspace_packages_found(self):
        result = _modules_dict("node-workspaces-glob")
        assert result["packages/ui"]["name"] == "@glob-mono/ui"
        assert result["packages/api"]["name"] == "@glob-mono/api"
        assert result["packages/shared"]["name"] == "@glob-mono/shared"

    def test_non_workspace_package_found_by_scanner(self):
        """tools/scripts is not in workspaces glob — scanner picks it up."""
        result = _modules_dict("node-workspaces-glob")
        assert "tools/scripts" in result
        assert result["tools/scripts"]["name"] == "build-scripts"

    def test_root_found(self):
        result = _modules_dict("node-workspaces-glob")
        assert result["."]["name"] == "glob-mono"

    def test_total_count(self):
        result = _modules_dict("node-workspaces-glob")
        assert len(result) == 5


class TestNodeNotInWorkspace:
    """Declared workspaces + a rogue package outside the workspace glob.
    Declarations find declared packages, scanner catches the rogue."""

    def test_declared_packages_found(self):
        result = _modules_dict("node-not-in-workspace")
        assert result["packages/declared-a"]["name"] == "declared-a"
        assert result["packages/declared-b"]["name"] == "declared-b"

    def test_rogue_package_found_by_scanner(self):
        """services/rogue-api exists but isn't in workspaces — scanner catches it."""
        result = _modules_dict("node-not-in-workspace")
        assert "services/rogue-api" in result
        assert result["services/rogue-api"]["name"] == "rogue-api"

    def test_total_count(self):
        """4 modules: root + 2 declared + 1 rogue."""
        result = _modules_dict("node-not-in-workspace")
        assert len(result) == 4


class TestNodePnpmWorkspace:
    """pnpm-workspace.yaml is not parsed by declarations layer.
    Scanner still finds all packages via recursive file walk."""

    def test_packages_found_by_scanner(self):
        result = _modules_dict("node-pnpm-workspace")
        assert result["packages/core"]["name"] == "@pnpm-mono/core"
        assert result["packages/cli"]["name"] == "@pnpm-mono/cli"

    def test_apps_found_by_scanner(self):
        result = _modules_dict("node-pnpm-workspace")
        assert result["apps/web"]["name"] == "@pnpm-mono/web"

    def test_all_from_scanner_not_declarations(self):
        """All sub-packages come from scanner (PACKAGE_JSON), not declarations."""
        result = _modules_dict("node-pnpm-workspace")
        for path in ("packages/core", "packages/cli", "apps/web"):
            assert result[path]["manifest"] == Manifest.PACKAGE_JSON

    def test_total_count(self):
        """4 modules: root + core + cli + web."""
        result = _modules_dict("node-pnpm-workspace")
        assert len(result) == 4


# --- JVM: Maven and Gradle variants ---


class TestJvmMavenNested:
    """Multi-level Maven: root declares parent-mod, parent-mod declares child-a/child-b.
    Declarations only parse root pom.xml, so only parent-mod is declared.
    Scanner catches the grandchildren."""

    def test_root_found(self):
        result = _modules_dict("jvm-maven-nested")
        assert result["."]["name"] == "com.acme:platform"

    def test_declared_parent_mod(self):
        result = _modules_dict("jvm-maven-nested")
        assert result["parent-mod"]["name"] == "com.acme:parent-mod"
        assert result["parent-mod"]["manifest"] == Manifest.POM_XML

    def test_grandchildren_found_by_scanner(self):
        """child-a and child-b are declared in parent-mod/pom.xml, not root.
        Our declarations layer only parses root — scanner catches these."""
        result = _modules_dict("jvm-maven-nested")
        assert result["parent-mod/child-a"]["name"] == "com.acme:child-a"
        assert result["parent-mod/child-b"]["name"] == "com.acme:child-b"

    def test_total_count(self):
        result = _modules_dict("jvm-maven-nested")
        assert len(result) == 4


class TestJvmGradleMixedDsl:
    """Gradle project with both Kotlin DSL (.kts) and Groovy (.gradle) build files,
    plus a findProject rename."""

    def test_find_project_rename(self):
        """services:rest-api is renamed to 'api' via findProject."""
        result = _modules_dict("jvm-gradle-mixed-dsl")
        assert result["services/rest-api"]["name"] == "api"

    def test_groovy_module_found(self):
        """batch-job uses build.gradle (Groovy), not .kts."""
        result = _modules_dict("jvm-gradle-mixed-dsl")
        assert result["services/batch-job"]["name"] == "batch-job"

    def test_all_declared_via_settings(self):
        result = _modules_dict("jvm-gradle-mixed-dsl")
        for path in ("services/rest-api", "services/batch-job", "libs/shared"):
            assert result[path]["manifest"] == Manifest.SETTINGS_GRADLE_KTS

    def test_root_found(self):
        result = _modules_dict("jvm-gradle-mixed-dsl")
        assert result["."]["name"] == "mixed-dsl-platform"

    def test_total_count(self):
        result = _modules_dict("jvm-gradle-mixed-dsl")
        assert len(result) == 4


class TestJvmMavenGradleCoexist:
    """Maven backend and Gradle frontend in the same repo. Tests that both
    build tools are discovered independently."""

    def test_maven_modules_found(self):
        result = _modules_dict("jvm-maven-gradle-coexist")
        assert result["."]["name"] == "com.acme:mono"
        assert result["backend"]["name"] == "com.acme:backend"
        assert result["backend/services/api"]["name"] == "com.acme:rest-api"

    def test_gradle_module_found(self):
        result = _modules_dict("jvm-maven-gradle-coexist")
        assert result["frontend"]["name"] == "frontend-build"
        assert result["frontend"]["manifest"] == Manifest.BUILD_GRADLE_KTS

    def test_both_ecosystems_are_java(self):
        """Maven and Gradle both map to Ecosystem.JAVA."""
        result = _modules_dict("jvm-maven-gradle-coexist")
        assert all(v["ecosystem"] == Ecosystem.JAVA for v in result.values())

    def test_total_count(self):
        result = _modules_dict("jvm-maven-gradle-coexist")
        assert len(result) == 4
