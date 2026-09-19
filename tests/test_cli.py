from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from packdesign import __version__
from packdesign.cli import main

ANALYZE_30Q = ["analyze", "--cell", "samsung-30q", "-s", "8", "-p", "2"]


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cells_text(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "cells")
    assert code == 0
    assert "samsung-30q" in out
    assert "Samsung INR18650-30Q" in out


def test_cells_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "cells", "--format", "json")
    assert code == 0
    ids = [cell["id"] for cell in json.loads(out)["cells"]]
    assert "molicel-p42a" in ids


def test_analyze_text(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, *ANALYZE_30Q)
    assert code == 0
    assert "Battery pack 8S2P" in out
    assert "20.0 / 28.8 / 33.6 V" in out
    assert "169.9 Wh" in out
    assert "40 A" in out
    assert "10 AWG" in out


def test_cells_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "cells", "--format", "markdown")
    assert code == 0
    assert out.startswith("# Cell library")
    assert "| samsung-50e | Samsung INR21700-50E | li-ion | 21700 | 3.63 | 4.90 |" in out


def test_zero_load_text_has_no_runtime_or_wiring(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, *ANALYZE_30Q, "--load", "0")
    assert code == 0
    assert "n/a (no load)" in out
    assert "Main wiring" not in out


def test_small_load_reports_runtime_in_hours(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, *ANALYZE_30Q, "--load", "2")
    assert code == 0
    assert "2.95 h" in out  # 5.9 Ah / 2 A


def test_analyze_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, *ANALYZE_30Q, "--format", "markdown")
    assert code == 0
    assert out.startswith("# Battery pack 8S2P")
    assert "| Energy | 169.9 Wh |" in out


def test_analyze_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, *ANALYZE_30Q, "--load", "15", "--format", "json")
    assert code == 0
    data: dict[str, Any] = json.loads(out)
    assert data["configuration"] == "8S2P"
    assert data["energy_wh"] == pytest.approx(169.92)
    assert data["load"]["current_a"] == 15
    assert data["main_wiring"]["fuse_rating_a"] == 20


def test_analyze_without_load_has_no_wiring(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, *ANALYZE_30Q, "--load", "0", "--format", "json")
    assert code == 0
    data = json.loads(out)
    assert "main_wiring" not in data
    assert data["load"]["ideal_runtime_h"] is None


def test_analyze_overload_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, *ANALYZE_30Q, "--load", "45")
    assert code == 0
    assert "NO - exceeds cell rating" in out


def test_design_text(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "design", "--voltage", "36", "--energy", "500", "--current", "20")
    assert code == 0
    assert "10S3P" in out
    assert "Pack design: 36 V nominal" in out


def test_design_top_and_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        capsys, "design", "--voltage", "48", "--energy", "700", "--chemistry", "li-ion",
        "--top", "1", "--show-rejected",
    )  # fmt: skip
    assert code == 0
    assert "4 more feasible design(s) not shown" in out
    rejected = out.split("Rejected")[1]
    assert "A123 Systems ANR26650M1-B: chemistry is lifepo4" in rejected


def test_design_shows_everything_when_top_is_large(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "design", "--voltage", "36", "--energy", "500", "--top", "10")
    assert code == 0
    assert "not shown" not in out
    assert "rejected" not in out.lower()
    assert "A123 Systems ANR26650M1-B" in out


def test_design_hides_rejections_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "design", "--voltage", "48", "--chemistry", "li-ion")
    assert code == 0
    assert "1 cell(s) rejected; use --show-rejected for reasons." in out


def test_design_nothing_feasible_lists_reasons(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "design", "--series", "20", "--max-voltage", "40")
    assert code == 0
    assert "No cell meets these requirements." in out
    assert "above the 40 V limit" in out


def test_design_markdown_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "design", "--series", "8", "--capacity", "6", "--format", "markdown")
    assert code == 0
    assert out.startswith("# Pack design: 8S, >= 6 Ah")
    code, out, _ = run(capsys, "design", "--series", "8", "--capacity", "6", "--format", "json")
    assert code == 0
    data = json.loads(out)
    assert data["candidates"][0]["rank"] == 1
    assert all(c["capacity_ah"] >= 6 for c in data["candidates"])


def test_custom_cells_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    custom = {
        "cells": [
            {
                "id": "my-cell",
                "manufacturer": "Acme",
                "model": "X1",
                "chemistry": "li-ion",
                "form_factor": "21700",
                "nominal_voltage_v": 3.6,
                "max_voltage_v": 4.2,
                "cutoff_voltage_v": 2.5,
                "capacity_ah": 4.0,
                "max_continuous_discharge_a": 20,
                "max_charge_a": 4,
                "internal_resistance_ohm": 0.015,
                "mass_kg": 0.068,
            }
        ]
    }
    path = tmp_path / "cells.json"
    path.write_text(json.dumps(custom), encoding="utf-8")
    code, out, _ = run(
        capsys, "analyze", "--cells-file", str(path), "--cell", "my-cell", "-s", "4", "-p", "1"
    )
    assert code == 0
    assert "Acme X1" in out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["analyze", "--cell", "nope", "-s", "8", "-p", "2"], "unknown cell 'nope'"),
        (["cells", "--cells-file", "does-not-exist.json"], "does-not-exist.json"),
        ([*ANALYZE_30Q, "--load", "400"], "non-positive terminal voltage"),
        ([*ANALYZE_30Q, "--max-drop", "150"], "max_drop_fraction"),
    ],
)
def test_errors_exit_with_code_1(
    capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    code, out, err = run(capsys, *argv)
    assert code == 1
    assert out == ""
    assert err.startswith("packdesign: error:")
    assert message in err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["analyze", "--cell", "samsung-30q", "-s", "0", "-p", "2"],
        ["analyze", "--cell", "samsung-30q", "-s", "8", "-p", "2", "--load", "-5"],
        ["design", "--energy", "500"],
        ["design", "--voltage", "36", "--series", "10"],
        ["design", "--voltage", "abc"],
        ["design", "--voltage", "inf"],
        ["design", "--series", "abc"],
        [*ANALYZE_30Q, "--load", "abc"],
        [*ANALYZE_30Q, "--load", "inf"],
    ],
)
def test_usage_errors_exit_with_code_2(capsys: pytest.CaptureFixture[str], argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2
    capsys.readouterr()


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_python_dash_m_entry_point() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    env = {**os.environ, "PYTHONPATH": str(src)}
    completed = subprocess.run(
        [sys.executable, "-m", "packdesign", "cells"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert "samsung-30q" in completed.stdout
