from pathlib import PurePosixPath, Path

from .declarations import discover_declared_modules
from .models import DiscoveredModule
from .scanner import discover_modules as scan_modules, SKIP_DIRS


def _in_skip_dir(module_path: str) -> bool:
    """Check if any segment of the module path is in the skip list."""
    if module_path == ".":
        return False
    return any(part in SKIP_DIRS for part in PurePosixPath(module_path).parts)


def discover_modules(repo_root: Path, depth: int = 4) -> list[DiscoveredModule]:
    """
    Discover all modules in a repository.

    1. Check explicit declarations (Maven <modules>, Gradle include(),
       Node workspaces, .NET *.sln)
    2. Fall back to recursive scan for everything else
    3. Filter out modules in skip directories
    4. Deduplicate by path

    Args:
        repo_root: Repository root directory.
        depth: Maximum directory depth for recursive scan.

    Returns:
        List of discovered modules, deduplicated by path.
    """
    # Phase 1: explicit declarations
    declared = discover_declared_modules(repo_root)

    # Phase 2: recursive scan
    scanned = scan_modules(repo_root, depth)

    # Deduplicate: declarations win over scan results for the same path+ecosystem
    # Filter: skip modules in excluded directories
    seen: set[tuple[str, str]] = set()
    results: list[DiscoveredModule] = []

    for module in declared + scanned:
        key = (module.path, module.ecosystem.value)
        if key not in seen and not _in_skip_dir(module.path):
            seen.add(key)
            results.append(module)

    return results
