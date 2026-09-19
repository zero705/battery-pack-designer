from __future__ import annotations

import pytest

from packdesign.cells import Cell, CellLibrary


@pytest.fixture(scope="session")
def library() -> CellLibrary:
    return CellLibrary.builtin()


@pytest.fixture
def cell_30q(library: CellLibrary) -> Cell:
    return library.get("samsung-30q")


@pytest.fixture
def ref_cell() -> Cell:
    """Round-number reference cell, so the maths tests don't depend on library data."""
    return Cell(
        id="ref",
        manufacturer="Reference",
        model="R18650",
        chemistry="li-ion",
        form_factor="18650",
        nominal_voltage_v=3.6,
        max_voltage_v=4.2,
        cutoff_voltage_v=2.5,
        capacity_ah=3.0,
        max_continuous_discharge_a=15.0,
        max_charge_a=4.0,
        internal_resistance_ohm=0.020,
        mass_kg=0.046,
    )


@pytest.fixture
def cell_kwargs() -> dict[str, object]:
    """A valid set of keyword arguments for :class:`Cell`."""
    return {
        "id": "test-cell",
        "manufacturer": "Acme",
        "model": "T-18650",
        "chemistry": "li-ion",
        "form_factor": "18650",
        "nominal_voltage_v": 3.6,
        "max_voltage_v": 4.2,
        "cutoff_voltage_v": 2.5,
        "capacity_ah": 3.0,
        "max_continuous_discharge_a": 10.0,
        "max_charge_a": 3.0,
        "internal_resistance_ohm": 0.02,
        "mass_kg": 0.045,
    }
