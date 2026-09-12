"""PowerShell serialization checks for gcloud dictionary-valued flags."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "gcloud_dictionary.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def _run(command: str, *, windows: bool) -> subprocess.CompletedProcess[str]:
    if POWERSHELL is None:
        pytest.skip("PowerShell is not installed")
    environment = os.environ.copy()
    environment["OS"] = "Windows_NT" if windows else "Unix"
    script_path = SCRIPT.resolve().as_posix().replace("'", "''")
    return subprocess.run(
        [
            POWERSHELL,
            "-ExecutionPolicy",
            "Bypass",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f". '{script_path}'; {command}",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.mark.parametrize(
    ("windows", "prefix"),
    [(True, "^^^^;^^^^"), (False, "^;^")],
)
def test_dictionary_encoder_preserves_commas_in_values(windows: bool, prefix: str) -> None:
    result = _run(
        "ConvertTo-GcloudDictionaryArgument -Entry "
        "@('ENABLED_CATEGORIES=PLANT,DOG,CAT','APP_ENV=production')",
        windows=windows,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (f"{prefix}ENABLED_CATEGORIES=PLANT,DOG,CAT;APP_ENV=production")


def test_dictionary_encoder_rejects_its_reserved_delimiter() -> None:
    result = _run(
        "ConvertTo-GcloudDictionaryArgument -Entry @('VALUE=unsafe;value')",
        windows=True,
    )

    assert result.returncode != 0
    assert "reserved ';' delimiter" in result.stderr
