"""
Unit tests for RetryLab package metadata, PEP 561 typing, and manifest integrity.
"""

import importlib
import json
from pathlib import Path
import pytest

import retrylab
from retrylab import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_manifest_in_exists():
    """Verify MANIFEST.in exists and includes essential release files."""
    manifest_path = REPO_ROOT / "MANIFEST.in"
    assert manifest_path.exists(), "MANIFEST.in must exist at repository root"
    content = manifest_path.read_text(encoding="utf-8")
    assert "include README.md" in content
    assert "include LICENSE" in content
    assert "include CHANGELOG.md" in content
    assert "include pyproject.toml" in content
    assert "include retrylab/py.typed" in content


def test_pep561_py_typed_marker():
    """Verify PEP 561 py.typed marker is present in package directory."""
    py_typed = REPO_ROOT / "retrylab" / "py.typed"
    assert py_typed.exists(), "retrylab/py.typed must exist for PEP 561 type support"


def test_version_synchronization():
    """Verify version consistency across pyproject.toml, Python, TypeScript, and Go SDKs."""
    # 1. pyproject.toml
    pyproject_path = REPO_ROOT / "pyproject.toml"
    content = pyproject_path.read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in content

    # 2. TypeScript package.json
    ts_pkg_path = REPO_ROOT / "sdk" / "ts" / "package.json"
    if ts_pkg_path.exists():
        ts_data = json.loads(ts_pkg_path.read_text(encoding="utf-8"))
        assert ts_data["version"] == __version__

    # 3. Go version.go
    go_ver_path = REPO_ROOT / "sdk" / "go" / "retrylab" / "version.go"
    if go_ver_path.exists():
        go_content = go_ver_path.read_text(encoding="utf-8")
        assert f'v{__version__}' in go_content


def test_subpackage_importability():
    """Verify all first-party subpackages import cleanly."""
    subpackages = [
        "retrylab.models",
        "retrylab.transport",
        "retrylab.idempotency",
        "retrylab.assertions",
        "retrylab.patterns",
        "retrylab.drift",
        "retrylab.latency",
        "retrylab.matrix",
        "retrylab.proxy",
        "retrylab.recorder",
        "retrylab.reporting",
        "retrylab.scenarios",
        "retrylab.security",
        "retrylab.tui",
        "retrylab.studio",
        "retrylab.webhooks",
        "retrylab.streaming",
        "retrylab.socket",
        "retrylab.grpc",
        "retrylab.benchmark",
        "retrylab.adapters.requests_adapter",
    ]
    for pkg in subpackages:
        mod = importlib.import_module(pkg)
        assert mod is not None, f"Failed to import subpackage {pkg}"


def test_studio_assets_embedded():
    """Verify Chaos Studio HTML asset renders without external file dependencies."""
    from retrylab.studio.assets import render_studio_html
    html = render_studio_html()
    assert "<!DOCTYPE html>" in html
    assert "RetryLab Chaos Studio" in html
    assert len(html) > 5000  # Full SPA embedded
