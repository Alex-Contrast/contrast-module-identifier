import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .models import DiscoveredModule, Ecosystem, Manifest


SKIP_DIRS = {
    "node_modules", "vendor", "vendors", "bower_components",
    "dist", "build", "target", "out", "bin", "obj",
    ".git", ".github", ".mvn", "gradle",
    "__pycache__", ".venv", "venv",
    "test", "tests", "testdata", "fixtures", "mock", "mocks",
    "buildSrc",
}

# Primary manifests per ecosystem, in priority order.
# For each directory, we pick the first match per ecosystem.
_PRIMARY_MANIFESTS: list[Manifest] = [
    # Node: package.json has the name, lock files don't
    Manifest.PACKAGE_JSON,
    # Java (Maven)
    Manifest.POM_XML,
    # Java (Gradle) - build file is the module marker
    Manifest.BUILD_GRADLE_KTS,
    Manifest.BUILD_GRADLE,
    # Java (sbt)
    Manifest.BUILD_SBT,
    # Python: pyproject.toml has the name, others fall back to dir name
    Manifest.PYPROJECT_TOML,
    Manifest.PIPFILE,
    Manifest.REQUIREMENTS_TXT,
    # Go
    Manifest.GO_MOD,
    # Ruby
    Manifest.GEMFILE,
    # .NET
    Manifest.PROJECT_ASSETS_JSON,
    Manifest.PACKAGES_CONFIG,
    # PHP: composer.json has the name
    Manifest.COMPOSER_JSON,
    # --- Lock files (low priority, dirname fallback) ---
    # Detected only when no primary manifest exists in the same directory.
    # Names will always be dirname fallback.
    Manifest.PACKAGE_LOCK_JSON,
    Manifest.YARN_LOCK,
    Manifest.PNPM_LOCK_YAML,
    Manifest.POETRY_LOCK,
    Manifest.GOPKG_LOCK,
    Manifest.GEMFILE_LOCK,
    Manifest.COMPOSER_LOCK,
]


def discover_modules(repo_root: Path, depth: int = 4) -> list[DiscoveredModule]:
    """
    Recursively scan a repository for modules.

    Args:
        repo_root: Repository root directory.
        depth: Maximum directory depth to scan.

    Returns:
        List of discovered modules.
    """
    results: list[DiscoveredModule] = []
    _scan_directory(repo_root, repo_root, depth, results)
    return results


def _scan_directory(
    dir_path: Path,
    repo_root: Path,
    remaining_depth: int,
    results: list[DiscoveredModule],
) -> None:
    if remaining_depth < 0:
        return

    # Check for primary manifests, one per ecosystem
    found: dict[Ecosystem, Manifest] = {}
    for manifest in _PRIMARY_MANIFESTS:
        eco = manifest.ecosystem
        if eco not in found and (dir_path / manifest.value).is_file():
            found[eco] = manifest

    # Check for contrast_security.yaml in this directory
    contrast_app_name = _contrast_app_name(dir_path)

    # Build a DiscoveredModule for each ecosystem found in this directory
    for eco, manifest in found.items():
        rel_path = str(dir_path.relative_to(repo_root)) if dir_path != repo_root else "."
        name = _extract_name(dir_path, manifest) or dir_path.name
        results.append(DiscoveredModule(
            name=name,
            path=rel_path,
            manifest=manifest,
            ecosystem=eco,
            contrast_app_name=contrast_app_name,
        ))

    # Recurse into subdirectories
    try:
        for child in sorted(dir_path.iterdir()):
            if child.is_dir() and child.name not in SKIP_DIRS:
                _scan_directory(child, repo_root, remaining_depth - 1, results)
    except PermissionError:
        pass


_CONTRAST_YAML_NAMES = ("contrast_security.yaml", "contrast.yaml")


def _contrast_app_name(dir_path: Path) -> Optional[str]:
    """Extract application.name from contrast_security.yaml if present."""
    for name in _CONTRAST_YAML_NAMES:
        yaml_path = dir_path / name
        if not yaml_path.is_file():
            continue
        try:
            # Simple line-based parse — avoids adding a yaml dependency.
            # Looking for:
            #   application:
            #     name: some-app-name
            lines = yaml_path.read_text(encoding="utf-8").splitlines()
            in_application = False
            for line in lines:
                stripped = line.strip()
                if stripped == "application:" or stripped.startswith("application:"):
                    # Check for inline: application: {name: foo}
                    after = stripped[len("application:"):].strip()
                    if after:
                        # Inline value — not the block form we expect
                        continue
                    in_application = True
                    continue
                if in_application:
                    if line.startswith((" ", "\t")):
                        if stripped.startswith("name:"):
                            val = stripped[len("name:"):].strip().strip("'\"")
                            if val:
                                return val
                    else:
                        in_application = False
        except Exception:
            continue
    return None


def _extract_name(dir_path: Path, manifest: Manifest) -> Optional[str]:
    """Extract module name from a manifest file. Returns None to fall back to dir name."""
    try:
        match manifest:
            case Manifest.PACKAGE_JSON:
                return _name_from_package_json(dir_path / manifest.value)
            case Manifest.POM_XML:
                return _name_from_pom_xml(dir_path / manifest.value)
            case Manifest.BUILD_GRADLE | Manifest.BUILD_GRADLE_KTS:
                return _name_from_gradle(dir_path)
            case Manifest.PYPROJECT_TOML:
                return _name_from_pyproject_toml(dir_path / manifest.value)
            case Manifest.GO_MOD:
                return _name_from_go_mod(dir_path / manifest.value)
            case Manifest.COMPOSER_JSON:
                return _name_from_composer_json(dir_path / manifest.value)
            case _:
                return None
    except Exception:
        return None


def _name_from_package_json(path: Path) -> Optional[str]:
    """Extract 'name' from package.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("name") or None


def _name_from_pom_xml(path: Path) -> Optional[str]:
    """Extract 'groupId:artifactId' from pom.xml."""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = ""
    # Handle Maven namespace
    match = re.match(r"\{(.+)\}", root.tag)
    if match:
        ns = f"{{{match.group(1)}}}"
    artifact_id = root.findtext(f"{ns}artifactId")
    if not artifact_id:
        return None
    group_id = root.findtext(f"{ns}groupId")
    if group_id:
        return f"{group_id}:{artifact_id}"
    return artifact_id


def _name_from_gradle(dir_path: Path) -> Optional[str]:
    """Extract rootProject.name from settings.gradle(.kts)."""
    for name in ("settings.gradle.kts", "settings.gradle"):
        settings = dir_path / name
        if settings.is_file():
            text = settings.read_text(encoding="utf-8")
            match = re.search(r'rootProject\.name\s*=\s*["\'](.+?)["\']', text)
            if match:
                return match.group(1)
    return None


def _name_from_pyproject_toml(path: Path) -> Optional[str]:
    """Extract project.name from pyproject.toml."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data.get("project", {}).get("name") or None


def _name_from_go_mod(path: Path) -> Optional[str]:
    """Extract module path from go.mod."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("module "):
            return line.split(None, 1)[1].strip()
    return None


def _name_from_composer_json(path: Path) -> Optional[str]:
    """Extract 'name' from composer.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("name") or None
