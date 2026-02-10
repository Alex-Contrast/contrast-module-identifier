"""Tests for module_identifier orchestrator (discover)."""

import json
from pathlib import Path

import pytest

from module_identifier.models import Ecosystem, Manifest
from module_identifier.discover import discover_modules, _in_skip_dir


@pytest.fixture
def tmp_repo(tmp_path):
    return tmp_path


class TestInSkipDir:
    def test_root_path(self):
        assert not _in_skip_dir(".")

    def test_normal_path(self):
        assert not _in_skip_dir("services/api")

    def test_test_dir(self):
        assert _in_skip_dir("test/something")
        assert _in_skip_dir("tests/unit")

    def test_nested_skip(self):
        assert _in_skip_dir("src/test/fixtures")
        assert _in_skip_dir("deep/node_modules/pkg")

    def test_build_output(self):
        assert _in_skip_dir("target/classes")
        assert _in_skip_dir("dist/bundle")


class TestDiscoverModulesOrchestrator:
    def test_declarations_win_over_scanner(self, tmp_repo):
        """Declarations should take priority for the same path+ecosystem."""
        # Gradle settings declares a module
        (tmp_repo / "settings.gradle.kts").write_text(
            'rootProject.name = "root"\n'
            'include("mod-a")\n'
        )
        mod_dir = tmp_repo / "mod-a"
        mod_dir.mkdir()
        # Module also has a build file (scanner would find it too)
        (mod_dir / "build.gradle.kts").write_text("")

        modules = discover_modules(tmp_repo)
        mod_a = [m for m in modules if m.path == "mod-a"]
        assert len(mod_a) == 1
        # Should come from declarations (settings.gradle.kts), not scanner (build.gradle.kts)
        assert mod_a[0].manifest == Manifest.SETTINGS_GRADLE_KTS

    def test_filters_test_dirs_from_declarations(self, tmp_repo):
        """Declared modules under test/ should be filtered out."""
        (tmp_repo / "pom.xml").write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modules>
        <module>src-mod</module>
        <module>test/test-mod</module>
    </modules>
</project>""")
        for path in ("src-mod", "test/test-mod"):
            d = tmp_repo / path
            d.mkdir(parents=True)
            (d / "pom.xml").write_text(f"""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <artifactId>{d.name}</artifactId>
</project>""")

        modules = discover_modules(tmp_repo)
        names = {m.name for m in modules}
        assert "src-mod" in names
        assert "test-mod" not in names

    def test_deduplicates_by_path_and_ecosystem(self, tmp_repo):
        """Same path + ecosystem from both sources should only appear once."""
        (tmp_repo / "package.json").write_text(json.dumps({
            "name": "root",
            "workspaces": ["pkg-a"],
        }))
        pkg = tmp_repo / "pkg-a"
        pkg.mkdir()
        (pkg / "package.json").write_text(json.dumps({"name": "pkg-a"}))

        modules = discover_modules(tmp_repo)
        pkg_a = [m for m in modules if m.path == "pkg-a"]
        assert len(pkg_a) == 1

    def test_mixed_ecosystems_same_dir_not_deduped(self, tmp_repo):
        """Different ecosystems in the same dir should both appear."""
        (tmp_repo / "package.json").write_text(json.dumps({"name": "frontend"}))
        (tmp_repo / "packages.config").write_text("<packages></packages>")

        modules = discover_modules(tmp_repo)
        assert len(modules) == 2

    def test_empty_repo(self, tmp_repo):
        assert discover_modules(tmp_repo) == []
