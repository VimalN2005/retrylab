"""
Tests verifying Go SDK module manifest, packaging, and unit test execution.
"""

from pathlib import Path
import shutil
import subprocess
import pytest


def test_go_sdk_files_exist():
    repo_root = Path(__file__).resolve().parent.parent
    go_sdk_dir = repo_root / "sdk" / "go"

    assert (go_sdk_dir / "go.mod").exists(), "sdk/go/go.mod must exist"
    assert (go_sdk_dir / "retrylab" / "transport.go").exists(), "transport.go must exist"
    assert (go_sdk_dir / "retrylab" / "auditor.go").exists(), "auditor.go must exist"
    assert (go_sdk_dir / "examples" / "stripe_resilience" / "main.go").exists(), "Go example must exist"

    mod_content = (go_sdk_dir / "go.mod").read_text(encoding="utf-8")
    assert "github.com/VimalN2005/retrylab/sdk/go" in mod_content


def test_go_sdk_tests_execution():
    go_bin = shutil.which("go")
    if not go_bin:
        pytest.skip("Go binary not found in system PATH")

    repo_root = Path(__file__).resolve().parent.parent
    go_sdk_dir = repo_root / "sdk" / "go"

    res = subprocess.run(
        [go_bin, "test", "./..."],
        cwd=str(go_sdk_dir),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode == 0, f"Go tests failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "PASS" in res.stdout or "ok" in res.stdout
