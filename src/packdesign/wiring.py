"""Main-current wire and fuse sizing.

Wire gauges follow the American Wire Gauge (AWG) definition, where the diameter of
gauge ``n`` is ``0.127 mm * 92 ** ((36 - n) / 39)``. Gauges ``1/0`` to ``4/0`` are
represented by the integers ``0`` to ``-3``.

A wire is accepted when it satisfies two independent rules:

* **Ampacity** - the conductor area times a design current density must cover the
  required current. The default of 8 A/mm2 is a conservative rule of thumb for short,
  single, silicone-insulated conductors in free air. Use a lower value for bundled
  or enclosed wiring and always check the wire manufacturer's rating.
* **Voltage drop** - the round-trip drop at the operating current must stay below a
  chosen fraction of the system voltage.

The fuse protects the wire, so the wire must be able to carry the fuse rating
continuously (see :func:`plan_main_wiring`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Resistivity of annealed copper at 20 degC (IACS), in ohm-metres.
COPPER_RESISTIVITY_OHM_M = 1.7241e-8
#: Default design current density in A/mm2 (see module docstring).
DEFAULT_CURRENT_DENSITY_A_PER_MM2 = 8.0
#: Default allowed voltage drop as a fraction of system voltage.
DEFAULT_MAX_DROP_FRACTION = 0.02
#: Default fuse rating margin over the continuous current.
DEFAULT_FUSE_MARGIN = 1.25
#: Common automotive / MIDI / ANL fuse ratings in amperes.
STANDARD_FUSE_RATINGS_A: tuple[float, ...] = (
    1, 2, 3, 5, 7.5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80, 100,
    125, 150, 175, 200, 225, 250, 300, 350, 400, 500,
)  # fmt: skip
#: Supported gauges, thickest (4/0 = -3) to thinnest (30).
THICKEST_GAUGE = -3
THINNEST_GAUGE = 30

_EPSILON = 1e-9


def _check_gauge(gauge: int) -> None:
    if isinstance(gauge, bool) or not isinstance(gauge, int):
        raise TypeError(f"gauge must be an int, got {gauge!r}")
    if not THICKEST_GAUGE <= gauge <= THINNEST_GAUGE:
        raise ValueError(f"gauge must be between {THICKEST_GAUGE} (4/0) and {THINNEST_GAUGE}")


def _check_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number, got {value!r}")


def awg_name(gauge: int) -> str:
    """Display name of a gauge: ``10`` -> ``"10"``, ``0`` -> ``"1/0"``, ``-3`` -> ``"4/0"``."""
    _check_gauge(gauge)
    return f"{1 - gauge}/0" if gauge <= 0 else str(gauge)


def awg_diameter_mm(gauge: int) -> float:
    """Conductor diameter in millimetres."""
    _check_gauge(gauge)
    return 0.127 * math.pow(92.0, (36 - gauge) / 39)


def awg_area_mm2(gauge: int) -> float:
    """Conductor cross-section in square millimetres."""
    return math.pi / 4 * awg_diameter_mm(gauge) ** 2


def resistance_ohm_per_m(gauge: int) -> float:
    """Copper resistance per metre of conductor at 20 degC."""
    return COPPER_RESISTIVITY_OHM_M / (awg_area_mm2(gauge) * 1e-6)


@dataclass(frozen=True)
class WireSelection:
    """A chosen conductor and its performance at the operating current."""

    gauge: int
    area_mm2: float
    ampacity_a: float
    one_way_length_m: float
    voltage_drop_v: float
    voltage_drop_fraction: float
    power_loss_w: float

    @property
    def awg(self) -> str:
        return awg_name(self.gauge)


@dataclass(frozen=True)
class ProtectionPlan:
    """Fuse and main wire for the pack output."""

    fuse_rating_a: float
    wire: WireSelection


def select_wire(
    current_a: float,
    one_way_length_m: float,
    system_voltage_v: float,
    *,
    max_drop_fraction: float = DEFAULT_MAX_DROP_FRACTION,
    current_density_a_per_mm2: float = DEFAULT_CURRENT_DENSITY_A_PER_MM2,
    min_ampacity_a: float = 0.0,
) -> WireSelection:
    """Pick the thinnest gauge that meets the ampacity and voltage-drop rules.

    Args:
        current_a: operating current used for the voltage-drop check.
        one_way_length_m: cable length from source to load; the return path is
            assumed to be equal, so the drop is computed over twice this length.
        system_voltage_v: voltage the drop fraction refers to.
        max_drop_fraction: allowed round-trip drop, e.g. ``0.02`` for 2 %.
        current_density_a_per_mm2: design current density for the ampacity rule.
        min_ampacity_a: extra ampacity floor, e.g. the fuse rating.

    Raises:
        ValueError: on invalid input or if even 4/0 is not enough.
    """
    _check_positive("current_a", current_a)
    _check_positive("one_way_length_m", one_way_length_m)
    _check_positive("system_voltage_v", system_voltage_v)
    _check_positive("current_density_a_per_mm2", current_density_a_per_mm2)
    if not 0 < max_drop_fraction < 1:
        raise ValueError(f"max_drop_fraction must be between 0 and 1, got {max_drop_fraction!r}")
    if not math.isfinite(min_ampacity_a) or min_ampacity_a < 0:
        raise ValueError(f"min_ampacity_a must be >= 0, got {min_ampacity_a!r}")

    required_ampacity = max(current_a, min_ampacity_a)
    allowed_drop = max_drop_fraction * system_voltage_v
    for gauge in range(THINNEST_GAUGE, THICKEST_GAUGE - 1, -1):
        area = awg_area_mm2(gauge)
        ampacity = area * current_density_a_per_mm2
        if ampacity + _EPSILON < required_ampacity:
            continue
        resistance = resistance_ohm_per_m(gauge) * 2 * one_way_length_m
        drop = current_a * resistance
        if drop <= allowed_drop + _EPSILON:
            return WireSelection(
                gauge=gauge,
                area_mm2=area,
                ampacity_a=ampacity,
                one_way_length_m=one_way_length_m,
                voltage_drop_v=drop,
                voltage_drop_fraction=drop / system_voltage_v,
                power_loss_w=current_a * drop,
            )
    raise ValueError(
        f"no gauge up to 4/0 carries {required_ampacity:g} A over {one_way_length_m:g} m "
        f"with at most {max_drop_fraction:.1%} drop; shorten the cable, relax the limits "
        "or use parallel conductors / busbars"
    )


def select_fuse(continuous_current_a: float, margin: float = DEFAULT_FUSE_MARGIN) -> float:
    """Smallest standard fuse rating >= ``continuous_current_a * margin``.

    The margin keeps the fuse from ageing or nuisance-tripping at full continuous load.
    """
    _check_positive("continuous_current_a", continuous_current_a)
    if not math.isfinite(margin) or margin < 1:
        raise ValueError(f"margin must be >= 1, got {margin!r}")
    target = continuous_current_a * margin
    for rating in STANDARD_FUSE_RATINGS_A:
        if rating + _EPSILON >= target:
            return rating
    raise ValueError(
        f"{target:g} A exceeds the largest standard fuse ({STANDARD_FUSE_RATINGS_A[-1]:g} A)"
    )


def plan_main_wiring(
    continuous_current_a: float,
    one_way_length_m: float,
    system_voltage_v: float,
    *,
    max_drop_fraction: float = DEFAULT_MAX_DROP_FRACTION,
    current_density_a_per_mm2: float = DEFAULT_CURRENT_DENSITY_A_PER_MM2,
    fuse_margin: float = DEFAULT_FUSE_MARGIN,
) -> ProtectionPlan:
    """Choose the main fuse, then a wire that can carry that fuse rating.

    The wire must survive any current the fuse lets through indefinitely, so its
    ampacity is checked against the fuse rating while the voltage drop is checked
    at the actual continuous current.
    """
    fuse = select_fuse(continuous_current_a, fuse_margin)
    wire = select_wire(
        continuous_current_a,
        one_way_length_m,
        system_voltage_v,
        max_drop_fraction=max_drop_fraction,
        current_density_a_per_mm2=current_density_a_per_mm2,
        min_ampacity_a=fuse,
    )
    return ProtectionPlan(fuse_rating_a=fuse, wire=wire)
