from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from packdesign.cells import Cell, CellLibrary, UnknownCellError


def test_builtin_library_loads_valid_unique_cells(library: CellLibrary) -> None:
    assert len(library) >= 6
    assert library.ids() == sorted(library.ids())
    assert "samsung-30q" in library
    assert "does-not-exist" not in library


def test_cell_derived_values(cell_30q: Cell) -> None:
    assert cell_30q.name == "Samsung INR18650-30Q"
    assert cell_30q.energy_wh == pytest.approx(3.6 * 2.95)


# Values transcribed from the manufacturer datasheets named in each cell's "source".
# (id, V nom, V max, V cut-off, Ah, max discharge A, max charge A, ohm, kg)
DATASHEET_VALUES = [
    ("samsung-30q", 3.6, 4.2, 2.5, 2.95, 15.0, 4.0, 0.026, 0.048),
    ("lg-hg2", 3.6, 4.2, 2.5, 3.0, 20.0, 4.0, 0.020, 0.047),
    ("samsung-35e", 3.6, 4.2, 2.65, 3.35, 8.0, 2.0, 0.035, 0.050),
    ("molicel-p42a", 3.6, 4.2, 2.5, 4.0, 45.0, 4.2, 0.016, 0.070),
    ("samsung-50e", 3.63, 4.2, 2.5, 4.9, 9.8, 4.9, 0.028, 0.0695),
    ("a123-26650", 3.3, 3.6, 2.0, 2.4, 50.0, 10.0, 0.006, 0.076),
]


@pytest.mark.parametrize("row", DATASHEET_VALUES, ids=lambda row: str(row[0]))
def test_builtin_cells_match_datasheets(library: CellLibrary, row: tuple[Any, ...]) -> None:
    cell = library.get(row[0])
    actual = (
        cell.id,
        cell.nominal_voltage_v,
        cell.max_voltage_v,
        cell.cutoff_voltage_v,
        cell.capacity_ah,
        cell.max_continuous_discharge_a,
        cell.max_charge_a,
        cell.internal_resistance_ohm,
        cell.mass_kg,
    )
    assert actual == row


def test_builtin_cells_cite_a_source(library: CellLibrary) -> None:
    assert len(DATASHEET_VALUES) == len(library)
    for cell in library:
        assert cell.source.strip(), f"{cell.id} has no source"


def test_library_iterates_sorted_by_id(library: CellLibrary) -> None:
    assert [c.id for c in library] == library.ids()


def test_unknown_cell_lists_available_ids(library: CellLibrary) -> None:
    with pytest.raises(UnknownCellError, match="samsung-30q"):
        library.get("nope")


def test_empty_library_reports_none() -> None:
    with pytest.raises(UnknownCellError, match="none"):
        CellLibrary([]).get("x")


def test_valid_cell_constructs(cell_kwargs: dict[str, Any]) -> None:
    assert Cell(**cell_kwargs).notes == ""


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "  ", "must not be empty"),
        ("chemistry", "nicd", "unknown chemistry"),
        ("capacity_ah", 0.0, "capacity_ah must be a positive number"),
        ("mass_kg", -1.0, "mass_kg must be a positive number"),
        ("internal_resistance_ohm", float("nan"), "must be a positive number"),
        ("cutoff_voltage_v", 3.7, "cutoff < nominal < max"),
        ("max_voltage_v", 3.5, "cutoff < nominal < max"),
    ],
)
def test_invalid_cells_are_rejected(
    cell_kwargs: dict[str, Any], field: str, value: object, message: str
) -> None:
    cell_kwargs[field] = value
    with pytest.raises(ValueError, match=message):
        Cell(**cell_kwargs)


def test_from_dict_round_trip(cell_kwargs: dict[str, Any]) -> None:
    cell = Cell(**cell_kwargs)
    assert Cell.from_dict(cell.to_dict()) == cell


def test_from_dict_reports_missing_fields(cell_kwargs: dict[str, Any]) -> None:
    del cell_kwargs["capacity_ah"]
    with pytest.raises(ValueError, match="missing field\\(s\\): capacity_ah"):
        Cell.from_dict(cell_kwargs)


def test_from_dict_reports_unknown_fields(cell_kwargs: dict[str, Any]) -> None:
    cell_kwargs["colour"] = "blue"
    with pytest.raises(ValueError, match="unknown field\\(s\\): colour"):
        Cell.from_dict(cell_kwargs)


@pytest.mark.parametrize("bad", ["3.0", True, None])
def test_from_dict_rejects_non_numbers(cell_kwargs: dict[str, Any], bad: object) -> None:
    cell_kwargs["capacity_ah"] = bad
    with pytest.raises(ValueError, match="must be a number"):
        Cell.from_dict(cell_kwargs)


def test_duplicate_ids_rejected(cell_kwargs: dict[str, Any]) -> None:
    cell = Cell(**cell_kwargs)
    with pytest.raises(ValueError, match="duplicate cell id"):
        CellLibrary([cell, cell])


def test_merged_library_overrides_by_id(library: CellLibrary, cell_kwargs: dict[str, Any]) -> None:
    cell_kwargs["id"] = "samsung-30q"
    cell_kwargs["capacity_ah"] = 9.9
    merged = library.merged(CellLibrary([Cell(**cell_kwargs)]))
    assert len(merged) == len(library)
    assert merged.get("samsung-30q").capacity_ah == 9.9
    assert library.get("samsung-30q").capacity_ah == 2.95


def test_from_json_file(tmp_path: Path, cell_kwargs: dict[str, Any]) -> None:
    path = tmp_path / "cells.json"
    path.write_text(json.dumps({"cells": [cell_kwargs]}), encoding="utf-8")
    assert CellLibrary.from_json_file(path).ids() == ["test-cell"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{not json", "invalid JSON"),
        ("[]", 'expected an object with a "cells" list'),
        ('{"cells": {}}', 'expected an object with a "cells" list'),
        ('{"cells": [42]}', "cell #1 must be an object"),
        ('{"cells": [{"id": "x"}]}', "missing field"),
    ],
)
def test_from_json_text_errors(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        CellLibrary.from_json_text(text, source="test")
