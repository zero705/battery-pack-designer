"""Series/parallel pack model.

A pack is ``series`` groups connected in series, each group made of ``parallel`` cells
connected in parallel (notation ``8S2P``). Voltages scale with the series count;
capacity and current capability scale with the parallel count.

The electrical model is intentionally simple and transparent: an ideal voltage source
at the nominal voltage behind the DC internal resistance of the cells. It is a good
first-order estimate for sizing; real voltage sag also depends on state of charge,
temperature and pulse duration. See ``docs/theory.md`` for the equations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from packdesign.cells import Cell

_EPSILON = 1e-9


@dataclass(frozen=True)
class LoadPoint:
    """Pack behaviour at a constant load current."""

    current_a: float
    c_rate: float
    voltage_under_load_v: float
    power_w: float
    heat_w: float
    heat_per_cell_w: float
    ideal_runtime_h: float | None
    within_discharge_limit: bool


@dataclass(frozen=True)
class PackConfig:
    """A pack built from ``series`` x ``parallel`` identical cells."""

    cell: Cell
    series: int
    parallel: int

    def __post_init__(self) -> None:
        for name in ("series", "parallel"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a whole number >= 1, got {value!r}")

    @property
    def label(self) -> str:
        """Conventional configuration label, e.g. ``8S2P``."""
        return f"{self.series}S{self.parallel}P"

    @property
    def cell_count(self) -> int:
        return self.series * self.parallel

    @property
    def nominal_voltage_v(self) -> float:
        return self.series * self.cell.nominal_voltage_v

    @property
    def max_voltage_v(self) -> float:
        """Voltage when fully charged."""
        return self.series * self.cell.max_voltage_v

    @property
    def min_voltage_v(self) -> float:
        """Voltage at the discharge cut-off."""
        return self.series * self.cell.cutoff_voltage_v

    @property
    def capacity_ah(self) -> float:
        return self.parallel * self.cell.capacity_ah

    @property
    def energy_wh(self) -> float:
        """Nominal energy (nominal voltage x capacity)."""
        return self.nominal_voltage_v * self.capacity_ah

    @property
    def cell_mass_kg(self) -> float:
        """Mass of the cells only (no holders, nickel, BMS or enclosure)."""
        return self.cell_count * self.cell.mass_kg

    @property
    def specific_energy_wh_per_kg(self) -> float:
        """Cell-level specific energy; a finished pack is typically 20-40 % lower."""
        return self.energy_wh / self.cell_mass_kg

    @property
    def max_continuous_current_a(self) -> float:
        return self.parallel * self.cell.max_continuous_discharge_a

    @property
    def max_charge_current_a(self) -> float:
        return self.parallel * self.cell.max_charge_a

    @property
    def internal_resistance_ohm(self) -> float:
        """DC resistance of the cells: R_cell x S / P (interconnects excluded)."""
        return self.cell.internal_resistance_ohm * self.series / self.parallel

    @property
    def max_continuous_power_w(self) -> float:
        """Output power at the maximum continuous current, including voltage sag."""
        return self.at_load(self.max_continuous_current_a).power_w

    def at_load(self, current_a: float) -> LoadPoint:
        """Evaluate the pack at a constant discharge current.

        Raises:
            ValueError: if the current is negative, not finite, or so high that the
                model predicts a non-positive terminal voltage.
        """
        if not math.isfinite(current_a) or current_a < 0:
            raise ValueError(f"load current must be a finite number >= 0, got {current_a!r}")
        voltage = self.nominal_voltage_v - current_a * self.internal_resistance_ohm
        if voltage <= 0:
            raise ValueError(
                f"{current_a:g} A is beyond what a {self.label} pack of {self.cell.name} "
                "can deliver (model predicts a non-positive terminal voltage)"
            )
        heat = current_a**2 * self.internal_resistance_ohm
        return LoadPoint(
            current_a=current_a,
            c_rate=current_a / self.capacity_ah,
            voltage_under_load_v=voltage,
            power_w=voltage * current_a,
            heat_w=heat,
            heat_per_cell_w=heat / self.cell_count,
            ideal_runtime_h=self.capacity_ah / current_a if current_a > 0 else None,
            within_discharge_limit=current_a <= self.max_continuous_current_a + _EPSILON,
        )
