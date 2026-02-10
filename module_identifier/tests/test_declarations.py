"""Tests for module_identifier declarations."""

import json
from pathlib import Path

import pytest

from module_identifier.models import Ecosystem, Manifest
from module_identifier.declarations import (
    discover_declared_modules,
    _maven_modules,
    _gradle_modules,
    _node_workspaces,
    _dotnet_solution_projects,
)


@pytest.fixture
def tmp_repo(tmp_path):
    return tmp_path


# --- Maven ---


class TestMavenModules:
    def test_finds_declared_modules(self, tmp_repo):
        (tmp_repo / "pom.xml").write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <modules>
        <module>service-a</module>
        <module>service-b</module>
    </modules>
</project>""")
        # Create module dirs with pom.xml
        for name in ("service-a", "service-b"):
            d = tmp_repo / name
            d.mkdir()
            (d / "pom.xml").write_text(f"""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <artifactId>{name}</artifactId>
</project>""")

        modules = _maven_modules(tmp_repo)
        assert len(modules) == 2
        names = {m.name for m in modules}
        assert names == {"service-a", "service-b"}
        assert all(m.manifest == Manifest.POM_XML for m in modules)

    def test_skips_missing_module_dir(self, tmp_repo):
        (tmp_repo / "pom.xml").write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modules><module>ghost</module></modules>
</project>""")
        modules = _maven_modules(tmp_repo)
        assert modules == []

    def test_no_modules_element(self, tmp_repo):
        (tmp_repo / "pom.xml").write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <artifactId>standalone</artifactId>
</project>""")
        modules = _maven_modules(tmp_repo)
        assert modules == []

    def test_no_pom(self, tmp_repo):
        modules = _maven_modules(tmp_repo)
        assert modules == []


# --- Gradle ---


class TestGradleModules:
    def test_kotlin_dsl_include(self, tmp_repo):
        (tmp_repo / "settings.gradle.kts").write_text(
            'rootProject.name = "my-project"\n'
            'include("module-a")\n'
            'include("module-b")\n'
        )
        for name in ("module-a", "module-b"):
            (tmp_repo / name).mkdir()

        modules = _gradle_modules(tmp_repo)
        assert len(modules) == 2
        names = {m.name for m in modules}
        assert names == {"module-a", "module-b"}

    def test_multi_arg_include(self, tmp_repo):
        (tmp_repo / "settings.gradle.kts").write_text(
            'include("mod-a", "mod-b", "mod-c")\n'
        )
        for name in ("mod-a", "mod-b", "mod-c"):
            (tmp_repo / name).mkdir()

        modules = _gradle_modules(tmp_repo)
        assert len(modules) == 3

    def test_colon_paths(self, tmp_repo):
        (tmp_repo / "settings.gradle.kts").write_text(
            'include("services:api")\n'
        )
        (tmp_repo / "services" / "api").mkdir(parents=True)

        modules = _gradle_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "api"
        assert modules[0].path == "services/api"

    def test_commented_out_include(self, tmp_repo):
        (tmp_repo / "settings.gradle.kts").write_text(
            '// include("disabled")\n'
            'include("enabled")\n'
        )
        (tmp_repo / "disabled").mkdir()
        (tmp_repo / "enabled").mkdir()

        modules = _gradle_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "enabled"

    def test_find_project_rename(self, tmp_repo):
        (tmp_repo / "settings.gradle.kts").write_text(
            'include("services:old-name")\n'
            'findProject(":services:old-name")?.name = "new-name"\n'
        )
        (tmp_repo / "services" / "old-name").mkdir(parents=True)

        modules = _gradle_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "new-name"

    def test_no_settings(self, tmp_repo):
        modules = _gradle_modules(tmp_repo)
        assert modules == []

    def test_groovy_dsl(self, tmp_repo):
        (tmp_repo / "settings.gradle").write_text(
            "include 'module-a'\n"
        )
        (tmp_repo / "module-a").mkdir()

        modules = _gradle_modules(tmp_repo)
        assert len(modules) == 1
        assert modules[0].manifest == Manifest.SETTINGS_GRADLE


# --- Node workspaces ---


class TestNodeWorkspaces:
    def test_array_workspaces(self, tmp_repo):
        (tmp_repo / "package.json").write_text(json.dumps({
            "name": "root",
            "workspaces": ["packages/*"],
        }))
        for name in ("pkg-a", "pkg-b"):
            d = tmp_repo / "packages" / name
            d.mkdir(parents=True)
            (d / "package.json").write_text(json.dumps({"name": name}))

        modules = _node_workspaces(tmp_repo)
        assert len(modules) == 2
        names = {m.name for m in modules}
        assert names == {"pkg-a", "pkg-b"}

    def test_object_workspaces(self, tmp_repo):
        (tmp_repo / "package.json").write_text(json.dumps({
            "name": "root",
            "workspaces": {"packages": ["apps/*"]},
        }))
        d = tmp_repo / "apps" / "web"
        d.mkdir(parents=True)
        (d / "package.json").write_text(json.dumps({"name": "web-app"}))

        modules = _node_workspaces(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "web-app"

    def test_no_workspaces(self, tmp_repo):
        (tmp_repo / "package.json").write_text(json.dumps({"name": "solo"}))
        modules = _node_workspaces(tmp_repo)
        assert modules == []

    def test_no_package_json(self, tmp_repo):
        modules = _node_workspaces(tmp_repo)
        assert modules == []

    def test_workspace_without_package_json(self, tmp_repo):
        (tmp_repo / "package.json").write_text(json.dumps({
            "workspaces": ["packages/*"],
        }))
        (tmp_repo / "packages" / "empty").mkdir(parents=True)
        modules = _node_workspaces(tmp_repo)
        assert modules == []


# --- .NET solution ---


class TestDotnetSolutionProjects:
    def test_parses_sln(self, tmp_repo):
        (tmp_repo / "App.sln").write_text(
            'Project("{FAE04EC0}") = "MyApp", "src\\MyApp\\MyApp.csproj", "{GUID}"\n'
            "EndProject\n"
        )
        (tmp_repo / "src" / "MyApp").mkdir(parents=True)

        modules = _dotnet_solution_projects(tmp_repo)
        assert len(modules) == 1
        assert modules[0].name == "MyApp"
        assert modules[0].path == "src/MyApp"

    def test_skips_solution_folders(self, tmp_repo):
        (tmp_repo / "App.sln").write_text(
            'Project("{2150E333}") = "SolutionFolder", "SolutionFolder", "{GUID}"\n'
            "EndProject\n"
        )
        modules = _dotnet_solution_projects(tmp_repo)
        assert modules == []

    def test_no_sln(self, tmp_repo):
        modules = _dotnet_solution_projects(tmp_repo)
        assert modules == []


# --- Orchestrator ---


class TestDiscoverDeclaredModules:
    def test_combines_all_ecosystems(self, tmp_repo):
        # Maven
        (tmp_repo / "pom.xml").write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modules><module>java-mod</module></modules>
</project>""")
        java_dir = tmp_repo / "java-mod"
        java_dir.mkdir()
        (java_dir / "pom.xml").write_text("""<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <artifactId>java-mod</artifactId>
</project>""")

        # Node
        (tmp_repo / "package.json").write_text(json.dumps({
            "workspaces": ["node-mod"],
        }))
        node_dir = tmp_repo / "node-mod"
        node_dir.mkdir()
        (node_dir / "package.json").write_text(json.dumps({"name": "node-mod"}))

        modules = discover_declared_modules(tmp_repo)
        ecosystems = {m.ecosystem for m in modules}
        assert Ecosystem.JAVA in ecosystems
        assert Ecosystem.NODE in ecosystems
