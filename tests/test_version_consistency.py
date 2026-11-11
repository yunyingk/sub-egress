import re
import tomllib
from pathlib import Path

from app.version import VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_version_matches_project_and_lockfile():
    with (ROOT / "pyproject.toml").open("rb") as project_file:
        project_version = tomllib.load(project_file)["project"]["version"]
    with (ROOT / "uv.lock").open("rb") as lock_file:
        locked_project = next(
            package
            for package in tomllib.load(lock_file)["package"]
            if package["name"] == "sub-egress"
        )

    assert VERSION == project_version
    assert locked_project["version"] == project_version


def test_changelog_starts_with_current_project_version():
    with (ROOT / "pyproject.toml").open("rb") as project_file:
        project_version = tomllib.load(project_file)["project"]["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text()

    assert re.search(rf"^## \[{re.escape(project_version)}\](?:\s|$)", changelog, re.MULTILINE)


def test_readme_version_badge_tracks_latest_github_release():
    readme = (ROOT / "README.md").read_text()

    assert "img.shields.io/github/v/release/yunyingk/sub-egress?label=version" in readme
    assert not re.search(r"img\.shields\.io/badge/version-[^-]+-", readme)


def test_docker_publish_uses_semver_release_tags():
    workflow = (ROOT / ".github/workflows/docker.yml").read_text()

    assert "tags: [ 'v*' ]" in workflow
    assert "type=semver,pattern={{version}}" in workflow
