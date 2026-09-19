"""Pack sizing: from requirements to ranked candidate designs.

For every cell in a library the solver picks the series count from the voltage
target, then the smallest parallel count that satisfies every requirement
(energy, capacity, discharge current and charge current). Cells that cannot meet
the constraints are reported with a reason instead of being silently dropped.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from packdesign.cells import CHEMISTRIES, Cell
from packdesign.pack import PackConfig

SORT_KEYS: tuple[str, ...] = ("mass", "cells", "energy")

_EPSILON = 1e-9


def _ceil(value: float) -> int:
    """Ceiling that ignores floating-point noise (2.0000000001 -> 2)."""
    return max(1, math.ceil(value - _EPSILON))


@dataclass(frozen=True)
class Requirements:
    """What the pack must achieve. Give either ``nominal_voltage_v`` or ``series``."""

    nominal_voltage_v: float | None = None
    series: int | None = None
    energy_wh: float | None = None
    capacity_ah: float | None = None
    continuous_current_a: float = 0.0
    charge_current_a: float = 0.0
    max_mass_kg: float | None = None
    max_voltage_v: float | None = None
    chemistry: str | None = None

    def __post_init__(self) -> None:
        if (self.nominal_voltage_v is None) == (self.series is None):
            raise ValueError("give exactly one of nominal_voltage_v or series")
        if self.series is not None and (
            isinstance(self.series, bool) or not isinstance(self.series, int) or self.series < 1
        ):
            raise ValueError(f"series must be a whole number >= 1, got {self.series!r}")
        positive_optional = {
            "nominal_voltage_v": self.nominal_voltage_v,
            "energy_wh": self.energy_wh,
            "capacity_ah": self.capacity_ah,
            "max_mass_kg": self.max_mass_kg,
            "max_voltage_v": self.max_voltage_v,
        }
        for name, value in positive_optional.items():
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be a positive number, got {value!r}")
        for name, current in (
            ("continuous_current_a", self.continuous_current_a),
            ("charge_current_a", self.charge_current_a),
        ):
            if not math.isfinite(current) or current < 0:
                raise ValueError(f"{name} must be >= 0, got {current!r}")
        if self.chemistry is not None and self.chemistry not in CHEMISTRIES:
            raise ValueError(
                f"unknown chemistry '{self.chemistry}' (expected one of: {', '.join(CHEMISTRIES)})"
            )

    def describe(self) -> str:
        """One-line, human-readable summary of the requirements."""
        parts = []
        if self.series is not None:
            parts.append(f"{self.series}S")
        else:
            parts.append(f"{self.nominal_voltage_v:g} V nominal")
        if self.energy_wh is not None:
            parts.append(f">= {self.energy_wh:g} Wh")
        if self.capacity_ah is not None:
            parts.append(f">= {self.capacity_ah:g} Ah")
        if self.continuous_current_a:
            parts.append(f"{self.continuous_current_a:g} A continuous")
        if self.charge_current_a:
            parts.append(f"{self.charge_current_a:g} A charge")
        if self.max_voltage_v is not None:
            parts.append(f"<= {self.max_voltage_v:g} V max")
        if self.max_mass_kg is not None:
            parts.append(f"<= {self.max_mass_kg:g} kg cells")
        if self.chemistry is not None:
            parts.append(self.chemistry)
        return ", ".join(parts)


@dataclass(frozen=True)
class Candidate:
    """A feasible pack plus the requirement that set its parallel count."""

    pack: PackConfig
    limiting_factor: str


@dataclass(frozen=True)
class Rejection:
    """A cell that cannot meet the requirements, and why."""

    cell: Cell
    reason: str


@dataclass(frozen=True)
class DesignResult:
    requirements: Requirements
    candidates: list[Candidate] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)


def size_pack(cell: Cell, req: Requirements) -> Candidate | Rejection:
    """Size a pack for one cell, or explain why it cannot be done."""
    if req.chemistry is not None and cell.chemistry != req.chemistry:
        return Rejection(cell, f"chemistry is {cell.chemistry}, {req.chemistry} required")

    if req.series is not None:
        series = req.series
    else:
        assert req.nominal_voltage_v is not None  # guaranteed by Requirements
        series = max(1, round(req.nominal_voltage_v / cell.nominal_voltage_v))

    if req.max_voltage_v is not None and series * cell.max_voltage_v > req.max_voltage_v + _EPSILON:
        return Rejection(
            cell,
            f"{series}S reaches {series * cell.max_voltage_v:.1f} V when full, "
            f"above the {req.max_voltage_v:g} V limit",
        )

    needs: dict[str, int] = {"minimum (1P)": 1}
    if req.energy_wh is not None:
        needs["energy"] = _ceil(req.energy_wh / (series * cell.energy_wh))
    if req.capacity_ah is not None:
        needs["capacity"] = _ceil(req.capacity_ah / cell.capacity_ah)
    if req.continuous_current_a > 0:
        needs["discharge current"] = _ceil(
            req.continuous_current_a / cell.max_continuous_discharge_a
        )
    if req.charge_current_a > 0:
        needs["charge current"] = _ceil(req.charge_current_a / cell.max_charge_a)

    limiting_factor = max(needs, key=lambda name: needs[name])
    pack = PackConfig(cell, series, needs[limiting_factor])

    if req.max_mass_kg is not None and pack.cell_mass_kg > req.max_mass_kg + _EPSILON:
        return Rejection(
            cell,
            f"{pack.label} needs {pack.cell_mass_kg:.2f} kg of cells, "
            f"above the {req.max_mass_kg:g} kg limit",
        )
    return Candidate(pack, limiting_factor)


def design_packs(cells: Iterable[Cell], req: Requirements, sort_by: str = "mass") -> DesignResult:
    """Size a pack for every cell and rank the feasible designs.

    Args:
        cells: cells to consider, e.g. a :class:`~packdesign.cells.CellLibrary`.
        req: the requirements.
        sort_by: ``"mass"`` (lightest first), ``"cells"`` (fewest cells first) or
            ``"energy"`` (most energy first).
    """
    if sort_by not in SORT_KEYS:
        raise ValueError(f"sort_by must be one of: {', '.join(SORT_KEYS)}")
    candidates: list[Candidate] = []
    rejections: list[Rejection] = []
    for cell in cells:
        outcome = size_pack(cell, req)
        if isinstance(outcome, Candidate):
            candidates.append(outcome)
        else:
            rejections.append(outcome)

    if sort_by == "mass":
        candidates.sort(key=lambda c: (c.pack.cell_mass_kg, -c.pack.energy_wh, c.pack.cell.id))
    elif sort_by == "cells":
        candidates.sort(key=lambda c: (c.pack.cell_count, c.pack.cell_mass_kg, c.pack.cell.id))
    else:
        candidates.sort(key=lambda c: (-c.pack.energy_wh, c.pack.cell_mass_kg, c.pack.cell.id))
    return DesignResult(req, candidates, rejections)
