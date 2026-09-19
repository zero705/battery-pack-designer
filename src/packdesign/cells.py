"""Cell definitions and the cell library.

A :class:`Cell` holds the datasheet values the rest of the package needs. Cells are
immutable and validated on creation, so an impossible cell (for example a cut-off
voltage above the nominal voltage) is rejected immediately instead of producing
misleading pack results later on.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, fields
from importlib import resources
from pathlib import Path
from typing import Any

#: Supported chemistry families. ``li-ion`` covers the 4.2 V NMC/NCA family.
CHEMISTRIES: tuple[str, ...] = ("li-ion", "lifepo4")

_NUMERIC_FIELDS: tuple[str, ...] = (
    "nominal_voltage_v",
    "max_voltage_v",
    "cutoff_voltage_v",
    "capacity_ah",
    "max_continuous_discharge_a",
    "max_charge_a",
    "internal_resistance_ohm",
    "mass_kg",
)
_TEXT_FIELDS: tuple[str, ...] = ("id", "manufacturer", "model", "chemistry", "form_factor")
_OPTIONAL_TEXT_FIELDS: tuple[str, ...] = ("notes", "source")


class UnknownCellError(LookupError):
    """Raised when a cell id is not present in a :class:`CellLibrary`."""


@dataclass(frozen=True)
class Cell:
    """A single battery cell described by its datasheet values.

    All values use SI units: volts, ampere-hours, amperes, ohms and kilograms.

    ``internal_resistance_ohm`` is used to estimate voltage sag and heat. A DC value
    is best; many datasheets only publish the 1 kHz AC impedance, which is lower
    than the DC resistance, so results based on it are optimistic.
    ``source`` records where the values come from (e.g. datasheet and revision).
    """

    id: str
    manufacturer: str
    model: str
    chemistry: str
    form_factor: str
    nominal_voltage_v: float
    max_voltage_v: float
    cutoff_voltage_v: float
    capacity_ah: float
    max_continuous_discharge_a: float
    max_charge_a: float
    internal_resistance_ohm: float
    mass_kg: float
    notes: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        for name in _TEXT_FIELDS:
            if not str(getattr(self, name)).strip():
                raise ValueError(f"cell field '{name}' must not be empty")
        if self.chemistry not in CHEMISTRIES:
            raise ValueError(
                f"{self.id}: unknown chemistry '{self.chemistry}' "
                f"(expected one of: {', '.join(CHEMISTRIES)})"
            )
        for name in _NUMERIC_FIELDS:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{self.id}: {name} must be a positive number, got {value!r}")
        if not self.cutoff_voltage_v < self.nominal_voltage_v < self.max_voltage_v:
            raise ValueError(
                f"{self.id}: voltages must satisfy cutoff < nominal < max "
                f"(got {self.cutoff_voltage_v} / {self.nominal_voltage_v} / {self.max_voltage_v})"
            )

    @property
    def name(self) -> str:
        """Human-readable name, e.g. ``Samsung INR18650-30Q``."""
        return f"{self.manufacturer} {self.model}"

    @property
    def energy_wh(self) -> float:
        """Nominal energy of one cell in watt-hours."""
        return self.nominal_voltage_v * self.capacity_ah

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Cell:
        """Create a cell from a mapping such as one entry of a JSON cell file.

        Raises:
            ValueError: if fields are missing, unknown or not convertible.
        """
        known = {f.name for f in fields(cls)}
        required = set(_TEXT_FIELDS) | set(_NUMERIC_FIELDS)
        cell_id = data.get("id", "<no id>")
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(f"cell {cell_id}: missing field(s): {', '.join(missing)}")
        unknown = sorted(set(data.keys()) - known)
        if unknown:
            raise ValueError(f"cell {cell_id}: unknown field(s): {', '.join(unknown)}")

        values: dict[str, Any] = {name: str(data[name]) for name in _TEXT_FIELDS}
        for name in _NUMERIC_FIELDS:
            raw = data[name]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"cell {cell_id}: field '{name}' must be a number, got {raw!r}")
            values[name] = float(raw)
        for name in _OPTIONAL_TEXT_FIELDS:
            values[name] = str(data.get(name, ""))
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        """Return the cell as a plain dictionary (JSON serialisable)."""
        return asdict(self)


class CellLibrary:
    """An immutable, id-indexed collection of cells."""

    def __init__(self, cells: Iterable[Cell]) -> None:
        index: dict[str, Cell] = {}
        for cell in cells:
            if cell.id in index:
                raise ValueError(f"duplicate cell id '{cell.id}'")
            index[cell.id] = cell
        self._cells = index

    def __len__(self) -> int:
        return len(self._cells)

    def __iter__(self) -> Iterator[Cell]:
        return iter(sorted(self._cells.values(), key=lambda c: c.id))

    def __contains__(self, cell_id: object) -> bool:
        return cell_id in self._cells

    def ids(self) -> list[str]:
        """Sorted list of all cell ids."""
        return sorted(self._cells)

    def get(self, cell_id: str) -> Cell:
        """Return the cell with ``cell_id``.

        Raises:
            UnknownCellError: if the id is not in the library.
        """
        try:
            return self._cells[cell_id]
        except KeyError:
            available = ", ".join(self.ids()) or "none"
            raise UnknownCellError(
                f"unknown cell '{cell_id}'. Available cells: {available}"
            ) from None

    def merged(self, other: CellLibrary) -> CellLibrary:
        """Return a new library containing both; cells in ``other`` win on id clashes."""
        combined = dict(self._cells)
        combined.update(other._cells)
        return CellLibrary(combined.values())

    @classmethod
    def from_json_text(cls, text: str, source: str = "<text>") -> CellLibrary:
        """Parse a library from JSON of the form ``{"cells": [ {...}, ... ]}``."""
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}: invalid JSON ({exc})") from None
        if not isinstance(document, dict) or not isinstance(document.get("cells"), list):
            raise ValueError(f'{source}: expected an object with a "cells" list')
        cells = []
        for position, entry in enumerate(document["cells"], start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"{source}: cell #{position} must be an object")
            try:
                cells.append(Cell.from_dict(entry))
            except ValueError as exc:
                raise ValueError(f"{source}: {exc}") from None
        return cls(cells)

    @classmethod
    def from_json_file(cls, path: str | Path) -> CellLibrary:
        """Load a library from a JSON file on disk."""
        file_path = Path(path)
        return cls.from_json_text(file_path.read_text(encoding="utf-8"), source=str(file_path))

    @classmethod
    def builtin(cls) -> CellLibrary:
        """The library of common cells shipped with the package."""
        text = resources.files("packdesign").joinpath("data/cells.json").read_text(encoding="utf-8")
        return cls.from_json_text(text, source="built-in cell library")
