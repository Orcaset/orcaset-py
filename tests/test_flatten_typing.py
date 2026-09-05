"""Run the typing contract with the dev dependency in this Python environment."""

import subprocess
import sys
from pathlib import Path


def test_flatten_typing_contract():
    config = Path(__file__).parent / "typing" / "pyrefly.toml"
    result = subprocess.run(
        [sys.executable, "-m", "pyrefly", "check", "--config", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
