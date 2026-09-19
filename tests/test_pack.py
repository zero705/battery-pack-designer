from __future__ import annotations

import pytest

from packdesign.cells import Cell
from packdesign.pack import PackConfig


def test_8s2p_reference_pack(ref_cell: Cell) -> None:
    pack = PackConfig(ref_cell, series=8, parallel=2)
    assert pack.label == "8S2P"
    assert pack.cell_count == 16
    assert pack.nominal_voltage_v == pytest.approx(28.8)
    assert pack.max_voltage_v == pytest.approx(33.6)
    assert pack.min_voltage_v == pytest.approx(20.0)
    assert pack.capacity_ah == pytest.approx(6.0)
    assert pack.energy_wh == pytest.approx(172.8)
    assert pack.internal_resistance_ohm == pytest.approx(0.08)
    assert pack.max_continuous_current_a == pytest.approx(30.0)
    assert pack.max_charge_current_a == pytest.approx(8.0)
    assert pack.cell_mass_kg == pytest.approx(0.736)
    assert pack.specific_energy_wh_per_kg == pytest.approx(172.8 / 0.736)
    # 30 A x (28.8 V - 30 A x 0.08 ohm) = 30 x 26.4
    assert pack.max_continuous_power_w == pytest.approx(792.0)


def test_8s2p_samsung_30q_datasheet_values(cell_30q: Cell) -> None:
    # 2950 mAh minimum, 26 mOhm (AC 1 kHz max) and 48 g max from the Samsung datasheet
    pack = PackConfig(cell_30q, series=8, parallel=2)
    assert pack.capacity_ah == pytest.approx(5.9)
    assert pack.energy_wh == pytest.approx(169.92)
    assert pack.internal_resistance_ohm == pytest.approx(0.104)
    assert pack.cell_mass_kg == pytest.approx(0.768)
    load = pack.at_load(30.0)
    assert load.voltage_under_load_v == pytest.approx(25.68)
    assert load.heat_w == pytest.approx(93.6)
    assert load.heat_per_cell_w == pytest.approx(5.85)


def test_load_point_at_rated_current(ref_cell: Cell) -> None:
    load = PackConfig(ref_cell, 8, 2).at_load(30.0)
    assert load.c_rate == pytest.approx(5.0)
    assert load.voltage_under_load_v == pytest.approx(26.4)
    assert load.power_w == pytest.approx(792.0)
    assert load.heat_w == pytest.approx(72.0)
    assert load.heat_per_cell_w == pytest.approx(4.5)
    assert load.ideal_runtime_h == pytest.approx(0.2)
    assert load.within_discharge_limit


def test_load_point_without_load(ref_cell: Cell) -> None:
    load = PackConfig(ref_cell, 8, 2).at_load(0.0)
    assert load.ideal_runtime_h is None
    assert load.heat_w == 0.0
    assert load.voltage_under_load_v == pytest.approx(28.8)


def test_load_above_rating_is_flagged(ref_cell: Cell) -> None:
    assert not PackConfig(ref_cell, 8, 2).at_load(30.5).within_discharge_limit


@pytest.mark.parametrize("current", [-1.0, float("nan"), float("inf")])
def test_invalid_load_current(ref_cell: Cell, current: float) -> None:
    with pytest.raises(ValueError, match="load current"):
        PackConfig(ref_cell, 8, 2).at_load(current)


def test_impossible_load_current(ref_cell: Cell) -> None:
    # 28.8 V / 0.08 ohm = 360 A would pull the terminal voltage to zero
    with pytest.raises(ValueError, match="non-positive terminal voltage"):
        PackConfig(ref_cell, 8, 2).at_load(360.0)


@pytest.mark.parametrize(("series", "parallel"), [(0, 1), (1, 0), (-2, 1), (2.0, 1), (True, 1)])
def test_invalid_configuration(ref_cell: Cell, series: object, parallel: object) -> None:
    with pytest.raises(ValueError, match="whole number >= 1"):
        PackConfig(ref_cell, series, parallel)  # type: ignore[arg-type]


def test_parallel_divides_and_series_multiplies_resistance(ref_cell: Cell) -> None:
    base = PackConfig(ref_cell, 4, 2).internal_resistance_ohm
    assert PackConfig(ref_cell, 8, 2).internal_resistance_ohm == pytest.approx(2 * base)
    assert PackConfig(ref_cell, 4, 4).internal_resistance_ohm == pytest.approx(base / 2)
