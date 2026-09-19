from __future__ import annotations

import math

import pytest

from packdesign.wiring import (
    STANDARD_FUSE_RATINGS_A,
    awg_area_mm2,
    awg_diameter_mm,
    awg_name,
    plan_main_wiring,
    resistance_ohm_per_m,
    select_fuse,
    select_wire,
)


@pytest.mark.parametrize(
    ("gauge", "diameter_mm"),
    [(-3, 11.684), (0, 8.252), (10, 2.588), (22, 0.644), (30, 0.255)],
)
def test_awg_diameters_match_standard_table(gauge: int, diameter_mm: float) -> None:
    assert awg_diameter_mm(gauge) == pytest.approx(diameter_mm, abs=1e-3)


def test_awg_10_area_and_resistance() -> None:
    assert awg_area_mm2(10) == pytest.approx(5.261, abs=1e-3)
    # Standard tables give ~3.277 mOhm/m for 10 AWG copper at 20 degC
    assert resistance_ohm_per_m(10) * 1000 == pytest.approx(3.277, abs=0.005)


@pytest.mark.parametrize(
    ("gauge", "name"), [(-3, "4/0"), (-1, "2/0"), (0, "1/0"), (1, "1"), (12, "12")]
)
def test_awg_names(gauge: int, name: str) -> None:
    assert awg_name(gauge) == name


@pytest.mark.parametrize("gauge", [-4, 31])
def test_gauge_out_of_range(gauge: int) -> None:
    with pytest.raises(ValueError, match="gauge must be between"):
        awg_diameter_mm(gauge)


def test_gauge_must_be_int() -> None:
    with pytest.raises(TypeError):
        awg_diameter_mm(10.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(("current", "fuse"), [(30, 40), (8, 10), (0.5, 1), (4, 5), (320, 400)])
def test_select_fuse(current: float, fuse: float) -> None:
    assert select_fuse(current) == fuse


def test_select_fuse_exact_match_is_accepted() -> None:
    assert select_fuse(32.0) == 40  # 32 x 1.25 = 40 exactly


def test_select_fuse_too_large() -> None:
    with pytest.raises(ValueError, match="largest standard fuse"):
        select_fuse(STANDARD_FUSE_RATINGS_A[-1])


@pytest.mark.parametrize(("current", "margin"), [(0, 1.25), (-5, 1.25), (10, 0.9)])
def test_select_fuse_invalid(current: float, margin: float) -> None:
    with pytest.raises(ValueError, match="must be"):
        select_fuse(current, margin)


def test_short_run_is_ampacity_limited() -> None:
    wire = select_wire(30, 0.5, 28.8)
    # 30 A / 8 A/mm2 = 3.75 mm2 -> 12 AWG (3.31) is too small, 11 AWG (4.17) fits
    assert wire.gauge == 11
    assert wire.ampacity_a >= 30
    assert wire.voltage_drop_fraction < 0.02


def test_long_run_is_voltage_drop_limited() -> None:
    # 30 A over 5 m one-way at 12 V with 2 % drop needs <= 0.8 mOhm/m -> 3 AWG
    wire = select_wire(30, 5.0, 12.0)
    assert wire.gauge == 3
    assert wire.voltage_drop_v <= 0.24
    assert resistance_ohm_per_m(4) > 0.8e-3 >= resistance_ohm_per_m(3)


def test_wire_losses_are_consistent() -> None:
    wire = select_wire(20, 1.0, 48.0)
    assert wire.power_loss_w == pytest.approx(20 * wire.voltage_drop_v)
    assert wire.voltage_drop_fraction == pytest.approx(wire.voltage_drop_v / 48.0)
    assert wire.awg == awg_name(wire.gauge)


def test_impossible_wire_raises() -> None:
    with pytest.raises(ValueError, match="no gauge up to 4/0"):
        select_wire(2000, 10.0, 12.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"current_a": 0},
        {"one_way_length_m": -1},
        {"system_voltage_v": math.inf},
        {"max_drop_fraction": 0},
        {"max_drop_fraction": 1.5},
        {"min_ampacity_a": -1},
        {"current_density_a_per_mm2": 0},
    ],
)
def test_select_wire_invalid(kwargs: dict[str, float]) -> None:
    args: dict[str, float] = {"current_a": 10, "one_way_length_m": 1, "system_voltage_v": 24}
    args.update(kwargs)
    with pytest.raises(ValueError, match="must be"):
        select_wire(**args)


def test_plan_sizes_wire_for_the_fuse() -> None:
    plan = plan_main_wiring(30, 0.5, 28.8)
    assert plan.fuse_rating_a == 40
    # The wire must carry the 40 A fuse rating: 40 / 8 = 5 mm2 -> 10 AWG (5.26 mm2)
    assert plan.wire.gauge == 10
    assert plan.wire.ampacity_a >= plan.fuse_rating_a
