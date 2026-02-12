import json
import re
# stdlib ElementTree is not vulnerable to XXE (no external entity support)
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .models import DiscoveredModule, Ecosystem, Manifest
from .scanner import _name_from_package_json, _name_from_pom_xml, _name_from_gradle


def discover_declared_modules(repo_root: Path) -> list[DiscoveredModule]:
    """
    Discover modules from explicit declarations in the repo root.

    Checks for:
    - Maven: <modules> in parent pom.xml
    - Gradle: include() in settings.gradle(.kts)
    - Node: workspaces in root package.json
    - .NET: project references in *.sln

    Args:
        repo_root: Repository root directory.

    Returns:
        List of discovered modules from explicit declarations.
    """
    results: list[DiscoveredModule] = []

    results.extend(_maven_modules(repo_root))
    results.extend(_gradle_modules(repo_root))
    results.extend(_node_workspaces(repo_root))
    results.extend(_dotnet_solution_projects(repo_root))

    return results


def _maven_modules(repo_root: Path) -> list[DiscoveredModule]:
    """Parse <modules> from parent pom.xml."""
    pom_path = repo_root / "pom.xml"
    if not pom_path.is_file():
        return []

    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        ns = ""
        match = re.match(r"\{(.+)\}", root.tag)
        if match:
            ns = f"{{{match.group(1)}}}"

        modules_el = root.find(f"{ns}modules")
        if modules_el is None:
            return []

        results = []
        for module_el in modules_el.findall(f"{ns}module"):
            module_dir = module_el.text
            if not module_dir:
                continue

            module_path = (repo_root / module_dir).resolve()
            if not module_path.is_relative_to(repo_root.resolve()):
                continue
            module_pom = module_path / "pom.xml"
            if module_pom.is_file():
                name = _name_from_pom_xml(module_pom) or module_path.name
                results.append(DiscoveredModule(
                    name=name,
                    path=module_dir,
                    manifest=Manifest.POM_XML,
                    ecosystem=Ecosystem.JAVA,
                ))

        return results
    except Exception:
        return []


def _gradle_modules(repo_root: Path) -> list[DiscoveredModule]:
    """Parse include() from settings.gradle(.kts)."""
    settings_path = None
    for name in ("settings.gradle.kts", "settings.gradle"):
        candidate = repo_root / name
        if candidate.is_file():
            settings_path = candidate
            break

    if not settings_path:
        return []

    try:
        text = settings_path.read_text(encoding="utf-8")
        manifest_type = Manifest.SETTINGS_GRADLE_KTS if settings_path.name.endswith(".kts") else Manifest.SETTINGS_GRADLE

        # Strip comments (// to end of line)
        lines = text.splitlines()
        uncommented = "\n".join(
            line for line in lines if not line.strip().startswith("//")
        )

        # Extract all quoted strings from include() calls
        # Matches: include("mod1", "mod2") or include ":mod1", ":mod2"
        included: list[str] = []
        for match in re.finditer(r'include\s*\(([^)]+)\)', uncommented):
            args = match.group(1)
            included.extend(re.findall(r'["\']([^"\']+)["\']', args))
        # Also match Groovy-style without parens: include ":mod1", ":mod2"
        for match in re.finditer(r'include\s+([^(\n]+)', uncommented):
            args = match.group(1)
            included.extend(re.findall(r'["\']([^"\']+)["\']', args))

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for item in included:
            if item not in seen:
                seen.add(item)
                unique.append(item)

        # Parse findProject renames: findProject(":path")?.name = "new-name"
        renames: dict[str, str] = {}
        for match in re.finditer(
            r'findProject\(\s*["\']([^"\']+)["\']\s*\)\??\s*\.\s*name\s*=\s*["\']([^"\']+)["\']',
            uncommented,
        ):
            renames[match.group(1)] = match.group(2)

        results = []
        for module_ref in unique:
            # Gradle uses : as path separator
            module_dir = module_ref.lstrip(":").replace(":", "/")
            module_path = (repo_root / module_dir).resolve()
            if not module_path.is_relative_to(repo_root.resolve()):
                continue

            if not module_path.is_dir():
                continue

            # Check for a rename, try both with and without leading colon
            name = renames.get(module_ref) or renames.get(":" + module_ref.lstrip(":"))
            if not name:
                # Use last segment as the name
                name = module_ref.split(":")[-1]

            results.append(DiscoveredModule(
                name=name,
                path=module_dir,
                manifest=manifest_type,
                ecosystem=Ecosystem.JAVA,
            ))

        return results
    except Exception:
        return []


def _node_workspaces(repo_root: Path) -> list[DiscoveredModule]:
    """Parse workspaces from root package.json."""
    pkg_path = repo_root / "package.json"
    if not pkg_path.is_file():
        return []

    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        workspaces = data.get("workspaces")
        if not workspaces:
            return []

        # workspaces can be a list or an object with "packages" key
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])

        if not isinstance(workspaces, list):
            return []

        # Expand glob patterns to actual directories
        results = []
        for pattern in workspaces:
            for match_path in sorted(repo_root.glob(pattern)):
                if not match_path.resolve().is_relative_to(repo_root.resolve()):
                    continue
                if not match_path.is_dir():
                    continue
                child_pkg = match_path / "package.json"
                if not child_pkg.is_file():
                    continue

                rel_path = str(match_path.relative_to(repo_root))
                name = _name_from_package_json(child_pkg) or match_path.name
                results.append(DiscoveredModule(
                    name=name,
                    path=rel_path,
                    manifest=Manifest.PACKAGE_JSON,
                    ecosystem=Ecosystem.NODE,
                ))

        return results
    except Exception:
        return []


def _dotnet_solution_projects(repo_root: Path) -> list[DiscoveredModule]:
    """Parse project references from *.sln files."""
    sln_files = list(repo_root.glob("*.sln"))
    if not sln_files:
        return []

    results = []
    seen_paths: set[str] = set()

    try:
        for sln_path in sln_files:
            text = sln_path.read_text(encoding="utf-8")

            # Match Project lines: Project("{...}") = "Name", "path\to\project.csproj", "{...}"
            for match in re.finditer(
                r'Project\("[^"]*"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+)"',
                text,
            ):
                project_name = match.group(1)
                project_file = match.group(2)

                # Skip solution folders (they don't have real paths)
                if not project_file.endswith((".csproj", ".fsproj", ".vbproj")):
                    continue

                # Normalize path separators
                project_rel = project_file.replace("\\", "/")
                module_dir = str(Path(project_rel).parent)

                if module_dir in seen_paths:
                    continue
                seen_paths.add(module_dir)

                # Verify directory exists and is within repo
                if not (repo_root / module_dir).resolve().is_relative_to(repo_root.resolve()):
                    continue
                if not (repo_root / module_dir).is_dir():
                    continue

                results.append(DiscoveredModule(
                    name=project_name,
                    path=module_dir,
                    manifest=Manifest.PACKAGES_CONFIG,
                    ecosystem=Ecosystem.DOTNET,
                ))

        return results
    except Exception:
        return []
