"""
Tests verifying TypeScript/Node.js SDK manifest, structure, and test execution.
"""

import json
from pathlib import Path
import shutil
import subprocess
import pytest


def test_ts_sdk_files_exist():
    repo_root = Path(__file__).resolve().parent.parent
    ts_dir = repo_root / "sdk" / "ts"

    assert (ts_dir / "package.json").exists(), "package.json must exist"
    assert (ts_dir / "tsconfig.json").exists(), "tsconfig.json must exist"
    assert (ts_dir / "src" / "index.ts").exists(), "src/index.ts must exist"
    assert (ts_dir / "src" / "fetch-interceptor.ts").exists(), "fetch-interceptor.ts must exist"
    assert (ts_dir / "src" / "auditor.ts").exists(), "auditor.ts must exist"
    assert (ts_dir / "src" / "axios-interceptor.ts").exists(), "axios-interceptor.ts must exist"
    assert (ts_dir / "examples" / "openai-agent-resilience.ts").exists(), "TS example must exist"

    pkg_data = json.loads((ts_dir / "package.json").read_text(encoding="utf-8"))
    assert pkg_data["name"] == "@retrylab/retrylab"


def test_ts_sdk_tests_execution():
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js binary not found in system PATH")

    repo_root = Path(__file__).resolve().parent.parent
    ts_dir = repo_root / "sdk" / "ts"

    res = subprocess.run(
        [node_bin, "--test", "test/*.test.ts"],
        cwd=str(ts_dir),
        shell=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode == 0, f"TypeScript tests failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "pass 8" in res.stdout or "pass" in res.stdout
