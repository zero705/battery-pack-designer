"""Keep the files in ``examples/`` and the snippets in the README working."""

from __future__ import annotations

from pathlib import Path

import pytest

from packdesign import CellLibrary, PackConfig, plan_main_wiring
from packdesign.report import render_cells

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path", sorted((ROOT / "examples").glob("*.json")), ids=lambda p: p.name)
def test_example_cell_files_are_valid(path: Path) -> None:
    assert len(CellLibrary.from_json_file(path)) >= 1


def test_render_cells_handles_an_empty_library() -> None:
    assert render_cells(CellLibrary([]), "text") == "No cells available.\n"


def test_readme_python_api_example() -> None:
    cell = CellLibrary.builtin().get("samsung-30q")
    pack = PackConfig(cell, series=8, parallel=2)
    load = pack.at_load(30.0)
    plan = plan_main_wiring(30.0, one_way_length_m=0.5, system_voltage_v=pack.nominal_voltage_v)

    assert f"{pack.label}: {pack.energy_wh:.1f} Wh" == "8S2P: 169.9 Wh"
    assert f"{load.voltage_under_load_v:.1f} V" == "25.7 V"
    assert f"{load.heat_per_cell_w:.2f} W" == "5.85 W"
    assert f"{plan.fuse_rating_a:g} A, {plan.wire.awg} AWG" == "40 A, 10 AWG"
