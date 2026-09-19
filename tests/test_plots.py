from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from packdesign.cells import Cell, CellLibrary
from packdesign.cli import main
from packdesign.design import Requirements
from packdesign.pack import PackConfig
from packdesign.plots import (
    MAX_SERIES,
    PlottingUnavailableError,
    load_sweep,
    plot_load,
    plot_tradeoff,
    tradeoff_sweep,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
E_BIKE = Requirements(nominal_voltage_v=36, energy_wh=500)

# --------------------------------------------------------------------------- data


def test_load_sweep_defaults_to_one_and_a_half_times_rated(ref_cell: Cell) -> None:
    sweep = load_sweep(PackConfig(ref_cell, 8, 2), points=31)
    assert len(sweep.currents_a) == 31
    assert sweep.currents_a[0] == 0
    assert sweep.currents_a[-1] == pytest.approx(45.0)
    assert sweep.voltages_v[0] == pytest.approx(28.8)
    assert sweep.heat_per_cell_w[0] == 0
    # 30 A is the 21st point (index 20): 28.8 - 30 x 0.08 = 26.4 V
    assert sweep.voltages_v[20] == pytest.approx(26.4)


def test_load_sweep_stops_before_the_model_collapses(ref_cell: Cell) -> None:
    sweep = load_sweep(PackConfig(ref_cell, 8, 2), max_current_a=1000)
    # 28.8 V / 0.08 ohm = 360 A predicts 0 V; the sweep ends at 95 % of that
    assert sweep.currents_a[-1] == pytest.approx(342.0)
    assert min(sweep.voltages_v) > 0


@pytest.mark.parametrize(
    ("kwargs", "message"), [({"points": 1}, "points"), ({"max_current_a": 0}, "max_current_a")]
)
def test_load_sweep_invalid(ref_cell: Cell, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_sweep(PackConfig(ref_cell, 8, 2), **kwargs)


def test_tradeoff_sweep(library: CellLibrary) -> None:
    data = tradeoff_sweep(library, E_BIKE, max_current_a=100)
    assert data.currents_a[0] == 0
    assert data.currents_a[-1] == 100
    assert len(data.currents_a) == 101
    by_id = {line.cell.id: line for line in data.series}
    assert [line.cell.id for line in data.series] == library.ids()
    # Same numbers as `packdesign design`: 50E is 10S3P at 20 A, HG2 10S5P at 60 A
    assert by_id["samsung-50e"].labels[20] == "10S3P"
    assert by_id["lg-hg2"].labels[60] == "10S5P"
    for line in data.series:
        masses = [m for m in line.masses_kg if m is not None]
        assert masses == sorted(masses), f"{line.cell.id} mass must never drop as current rises"


def test_tradeoff_keeps_filtered_cells_as_empty_series(library: CellLibrary) -> None:
    data = tradeoff_sweep(
        library, Requirements(nominal_voltage_v=12.8, energy_wh=100, chemistry="lifepo4"), 50
    )
    feasible = [line.cell.id for line in data.series if any(m is not None for m in line.masses_kg)]
    assert feasible == ["a123-26650"]
    assert len(data.series) == len(library)  # colour slots stay reserved


def _many_cells(count: int, template: Cell) -> list[Cell]:
    return [Cell(**{**template.to_dict(), "id": f"c{i}"}) for i in range(count)]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_current_a": 0}, "max_current_a"),
        ({"max_current_a": 10, "step_a": 0}, "step_a"),
    ],
)
def test_tradeoff_sweep_invalid(library: CellLibrary, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        tradeoff_sweep(library, E_BIKE, **kwargs)


def test_tradeoff_sweep_cell_count_limits(ref_cell: Cell) -> None:
    with pytest.raises(ValueError, match="no cells"):
        tradeoff_sweep([], E_BIKE, 10)
    with pytest.raises(ValueError, match=f"at most {MAX_SERIES} cells"):
        tradeoff_sweep(_many_cells(MAX_SERIES + 1, ref_cell), E_BIKE, 10)


# --------------------------------------------------------------------------- rendering

matplotlib = pytest.importorskip("matplotlib")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_plot_load_writes_png(tmp_path: Path, cell_30q: Cell, theme: str) -> None:
    out = plot_load(load_sweep(PackConfig(cell_30q, 8, 2)), tmp_path / "load.png", theme=theme)
    assert out.read_bytes().startswith(PNG_SIGNATURE)


def test_plot_load_when_rated_current_is_off_the_axis(tmp_path: Path, cell_30q: Cell) -> None:
    sweep = load_sweep(PackConfig(cell_30q, 8, 2), max_current_a=20)
    out = plot_load(sweep, tmp_path / "load.svg")
    assert "<svg" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_plot_tradeoff_writes_png(tmp_path: Path, library: CellLibrary, theme: str) -> None:
    data = tradeoff_sweep(library, E_BIKE, 100)
    out = plot_tradeoff(data, tmp_path / "t.png", theme=theme, highlight=["samsung-50e"])
    assert out.read_bytes().startswith(PNG_SIGNATURE)


def test_plot_tradeoff_skips_filtered_cells(tmp_path: Path, library: CellLibrary) -> None:
    data = tradeoff_sweep(
        library, Requirements(nominal_voltage_v=12.8, energy_wh=100, chemistry="lifepo4"), 50
    )
    assert plot_tradeoff(data, tmp_path / "lfp.png").exists()


def test_cli_plot_tradeoff_mass_limit_ends_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # With a 3 kg limit the 50E stops being feasible above ~40 A: its line ends early
    out = tmp_path / "limited.png"
    argv = ["plot", "tradeoff", "--voltage", "36", "--energy", "500", "--max-mass", "3"]
    assert main([*argv, "-o", str(out)]) == 0
    assert out.exists()
    capsys.readouterr()


def test_plot_tradeoff_with_nothing_feasible(tmp_path: Path, library: CellLibrary) -> None:
    data = tradeoff_sweep(library, Requirements(series=20, energy_wh=100, max_voltage_v=10), 10)
    with pytest.raises(ValueError, match="nothing to plot"):
        plot_tradeoff(data, tmp_path / "none.png")


def test_plot_errors(tmp_path: Path, cell_30q: Cell) -> None:
    sweep = load_sweep(PackConfig(cell_30q, 8, 2))
    with pytest.raises(ValueError, match="theme"):
        plot_load(sweep, tmp_path / "x.png", theme="neon")
    with pytest.raises(OSError, match="folder does not exist"):
        plot_load(sweep, tmp_path / "missing" / "x.png")


def test_missing_matplotlib_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cell_30q: Cell
) -> None:
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    with pytest.raises(PlottingUnavailableError, match="pip install"):
        plot_load(load_sweep(PackConfig(cell_30q, 8, 2)), tmp_path / "x.png")


# --------------------------------------------------------------------------- CLI


def test_cli_plot_load(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "load.png"
    code = main(["plot", "load", "--cell", "samsung-30q", "-s", "8", "-p", "2", "-o", str(out)])
    assert code == 0
    assert out.read_bytes().startswith(PNG_SIGNATURE)
    assert "Saved" in capsys.readouterr().out


def test_cli_plot_tradeoff(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "tradeoff.png"
    argv = ["plot", "tradeoff", "--voltage", "36", "--energy", "500", "--max-current", "60"]
    code = main([*argv, "--highlight", "lg-hg2", "--theme", "dark", "-o", str(out)])
    assert code == 0
    assert out.exists()
    capsys.readouterr()


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--highlight", "nope"], "unknown cell 'nope'"),
        (["--max-voltage", "10"], "nothing to plot"),
    ],
)
def test_cli_plot_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    argv = ["plot", "tradeoff", "--voltage", "36", "--energy", "500", "-o", str(tmp_path / "x.png")]
    assert main([*argv, *extra]) == 1
    assert message in capsys.readouterr().err


def test_cli_plot_without_matplotlib(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    argv = [
        "plot",
        "load",
        "--cell",
        "samsung-30q",
        "-s",
        "8",
        "-p",
        "2",
        "-o",
        str(tmp_path / "x.png"),
    ]
    assert main(argv) == 1
    assert "charts need matplotlib" in capsys.readouterr().err
