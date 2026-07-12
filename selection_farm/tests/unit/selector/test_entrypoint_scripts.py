import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = (
    PROJECT_ROOT / "scripts/run_selector.sh",
    PROJECT_ROOT / "scripts/run_selector_llm.sh",
    PROJECT_ROOT / "scripts/run_selector_ml.sh",
)


def test_selector_scripts_are_cwd_independent_and_use_project_venv() -> None:
    for script in SCRIPTS:
        source = script.read_text(encoding="utf-8")
        assert "BASH_SOURCE[0]" in source
        assert "venv_ai_selection_farm/bin/python" in source or script.name == "run_selector.sh"


@pytest.mark.parametrize("script", SCRIPTS)
def test_selector_scripts_pass_shell_syntax(script: Path) -> None:
    result = subprocess.run(["bash", "-n", script], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_dispatcher_requires_an_explicit_allowlisted_branch(tmp_path: Path) -> None:
    dispatcher = SCRIPTS[0]
    missing = subprocess.run(
        [dispatcher], cwd=tmp_path, check=False, capture_output=True, text=True
    )
    unknown = subprocess.run(
        [dispatcher, "--branch", "unknown"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert missing.returncode == 2
    assert unknown.returncode == 2
    assert "Unsupported Selector branch" in unknown.stderr
