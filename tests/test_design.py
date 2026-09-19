from __future__ import annotations

from typing import Any

import pytest

from packdesign.cells import CellLibrary
from packdesign.design import Candidate, Rejection, Requirements, design_packs, size_pack


def test_ebike_pack_with_50e(library: CellLibrary) -> None:
    req = Requirements(nominal_voltage_v=36, energy_wh=500, continuous_current_a=20)
    outcome = size_pack(library.get("samsung-50e"), req)
    assert isinstance(outcome, Candidate)
    # 36 V / 3.63 V -> 10S; energy needs ceil(500 / 177.9) = 3P; current ceil(20 / 9.8) = 3P
    assert outcome.pack.label == "10S3P"
    assert outcome.pack.energy_wh >= 500


def test_current_can_be_the_limiting_factor(library: CellLibrary) -> None:
    req = Requirements(nominal_voltage_v=36, energy_wh=100, continuous_current_a=40)
    outcome = size_pack(library.get("samsung-35e"), req)
    assert isinstance(outcome, Candidate)
    assert outcome.pack.parallel == 5  # 40 A / 8 A
    assert outcome.limiting_factor == "discharge current"


def test_charge_current_can_be_the_limiting_factor(library: CellLibrary) -> None:
    req = Requirements(series=8, charge_current_a=10)
    outcome = size_pack(library.get("samsung-35e"), req)
    assert isinstance(outcome, Candidate)
    assert outcome.pack.label == "8S5P"  # 10 A / 2 A
    assert outcome.limiting_factor == "charge current"


def test_capacity_requirement(library: CellLibrary) -> None:
    outcome = size_pack(library.get("lg-hg2"), Requirements(series=8, capacity_ah=6))
    assert isinstance(outcome, Candidate)
    assert outcome.pack.label == "8S2P"
    assert outcome.limiting_factor == "capacity"


def test_exact_fit_does_not_round_up(library: CellLibrary) -> None:
    # LG HG2: 8 x 10.8 Wh x 2 = 172.8 Wh exactly: must stay 2P despite float noise
    outcome = size_pack(library.get("lg-hg2"), Requirements(series=8, energy_wh=172.8))
    assert isinstance(outcome, Candidate)
    assert outcome.pack.parallel == 2


def test_lifepo4_12v_is_4s(library: CellLibrary) -> None:
    outcome = size_pack(
        library.get("a123-26650"), Requirements(nominal_voltage_v=12.8, capacity_ah=9.6)
    )
    assert isinstance(outcome, Candidate)
    assert outcome.pack.label == "4S4P"


def test_max_voltage_rejection(library: CellLibrary) -> None:
    outcome = size_pack(
        library.get("samsung-30q"), Requirements(nominal_voltage_v=48, max_voltage_v=50)
    )
    assert isinstance(outcome, Rejection)
    assert "above the 50 V limit" in outcome.reason


def test_mass_rejection(library: CellLibrary) -> None:
    outcome = size_pack(
        library.get("samsung-30q"), Requirements(series=10, energy_wh=1000, max_mass_kg=1)
    )
    assert isinstance(outcome, Rejection)
    assert "kg limit" in outcome.reason


def test_chemistry_filter(library: CellLibrary) -> None:
    result = design_packs(library, Requirements(nominal_voltage_v=12.8, chemistry="lifepo4"))
    assert [c.pack.cell.id for c in result.candidates] == ["a123-26650"]
    assert len(result.rejections) == len(library) - 1
    assert all("chemistry" in r.reason for r in result.rejections)


@pytest.mark.parametrize("sort_by", ["mass", "cells", "energy"])
def test_sorting(library: CellLibrary, sort_by: str) -> None:
    req = Requirements(nominal_voltage_v=36, energy_wh=500, continuous_current_a=20)
    candidates = design_packs(library, req, sort_by=sort_by).candidates
    assert len(candidates) == len(library)
    keys: list[float] = {
        "mass": [c.pack.cell_mass_kg for c in candidates],
        "cells": [float(c.pack.cell_count) for c in candidates],
        "energy": [-c.pack.energy_wh for c in candidates],
    }[sort_by]
    assert keys == sorted(keys)


def test_invalid_sort_key(library: CellLibrary) -> None:
    with pytest.raises(ValueError, match="sort_by"):
        design_packs(library, Requirements(series=4), sort_by="price")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "exactly one of"),
        ({"nominal_voltage_v": 36, "series": 10}, "exactly one of"),
        ({"series": 0}, "whole number"),
        ({"nominal_voltage_v": -1}, "nominal_voltage_v must be a positive number"),
        ({"series": 4, "energy_wh": 0}, "energy_wh must be a positive number"),
        ({"series": 4, "continuous_current_a": -1}, "continuous_current_a must be >= 0"),
        ({"series": 4, "chemistry": "lead-acid"}, "unknown chemistry"),
    ],
)
def test_invalid_requirements(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Requirements(**kwargs)


def test_describe_mentions_every_requirement() -> None:
    text = Requirements(
        nominal_voltage_v=36,
        energy_wh=500,
        continuous_current_a=20,
        charge_current_a=5,
        max_voltage_v=45,
        max_mass_kg=3,
        chemistry="li-ion",
    ).describe()
    for part in (
        "36 V nominal",
        ">= 500 Wh",
        "20 A continuous",
        "5 A charge",
        "<= 45 V",
        "<= 3 kg",
        "li-ion",
    ):
        assert part in text
    assert Requirements(series=8, capacity_ah=6).describe() == "8S, >= 6 Ah"
