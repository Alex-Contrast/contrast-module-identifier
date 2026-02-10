from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Ecosystem(str, Enum):
    JAVA = "java"
    NODE = "node"
    PYTHON = "python"
    GO = "go"
    RUBY = "ruby"
    DOTNET = "dotnet"
    PHP = "php"


class Manifest(str, Enum):
    # Node
    PACKAGE_JSON = "package.json"
    PACKAGE_LOCK_JSON = "package-lock.json"
    YARN_LOCK = "yarn.lock"
    PNPM_LOCK_YAML = "pnpm-lock.yaml"
    # Java (Maven)
    POM_XML = "pom.xml"
    # Java (Gradle)
    BUILD_GRADLE = "build.gradle"
    BUILD_GRADLE_KTS = "build.gradle.kts"
    SETTINGS_GRADLE = "settings.gradle"
    SETTINGS_GRADLE_KTS = "settings.gradle.kts"
    # Java (Scala/sbt)
    BUILD_SBT = "build.sbt"
    # Python
    PYPROJECT_TOML = "pyproject.toml"
    PIPFILE = "Pipfile"
    REQUIREMENTS_TXT = "requirements.txt"
    POETRY_LOCK = "poetry.lock"
    # Go
    GO_MOD = "go.mod"
    GOPKG_LOCK = "Gopkg.lock"
    # Ruby
    GEMFILE = "Gemfile"
    GEMFILE_LOCK = "Gemfile.lock"
    # .NET
    PROJECT_ASSETS_JSON = "project.assets.json"
    PACKAGES_CONFIG = "packages.config"
    # PHP
    COMPOSER_JSON = "composer.json"
    COMPOSER_LOCK = "composer.lock"

    @property
    def ecosystem(self) -> Ecosystem:
        return _MANIFEST_ECOSYSTEMS[self]


_MANIFEST_ECOSYSTEMS: dict[Manifest, Ecosystem] = {
    Manifest.PACKAGE_JSON: Ecosystem.NODE,
    Manifest.PACKAGE_LOCK_JSON: Ecosystem.NODE,
    Manifest.YARN_LOCK: Ecosystem.NODE,
    Manifest.PNPM_LOCK_YAML: Ecosystem.NODE,
    Manifest.POM_XML: Ecosystem.JAVA,
    Manifest.BUILD_GRADLE: Ecosystem.JAVA,
    Manifest.BUILD_GRADLE_KTS: Ecosystem.JAVA,
    Manifest.SETTINGS_GRADLE: Ecosystem.JAVA,
    Manifest.SETTINGS_GRADLE_KTS: Ecosystem.JAVA,
    Manifest.BUILD_SBT: Ecosystem.JAVA,
    Manifest.PYPROJECT_TOML: Ecosystem.PYTHON,
    Manifest.PIPFILE: Ecosystem.PYTHON,
    Manifest.REQUIREMENTS_TXT: Ecosystem.PYTHON,
    Manifest.POETRY_LOCK: Ecosystem.PYTHON,
    Manifest.GO_MOD: Ecosystem.GO,
    Manifest.GOPKG_LOCK: Ecosystem.GO,
    Manifest.GEMFILE: Ecosystem.RUBY,
    Manifest.GEMFILE_LOCK: Ecosystem.RUBY,
    Manifest.PROJECT_ASSETS_JSON: Ecosystem.DOTNET,
    Manifest.PACKAGES_CONFIG: Ecosystem.DOTNET,
    Manifest.COMPOSER_JSON: Ecosystem.PHP,
    Manifest.COMPOSER_LOCK: Ecosystem.PHP,
}


class DiscoveredModule(BaseModel):
    name: str = Field(description="Module name extracted from manifest, or directory name as fallback")
    path: str = Field(description="Relative path from repo root to the module directory")
    manifest: Manifest = Field(description="The manifest file that identified this module")
    ecosystem: Ecosystem = Field(description="The ecosystem/language of this module")
    contrast_app_name: Optional[str] = Field(
        default=None,
        description="Application name from contrast_security.yaml if present in module directory",
    )
