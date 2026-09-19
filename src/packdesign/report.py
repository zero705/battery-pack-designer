"""Render results as plain text, Markdown or JSON-ready dictionaries.

Output is ASCII-only so it prints safely on every terminal and code page.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from packdesign.cells import Cell
from packdesign.design import DesignResult
from packdesign.pack import LoadPoint, PackConfig
from packdesign.wiring import ProtectionPlan

FORMATS: tuple[str, ...] = ("text", "markdown", "json")

MODEL_NOTES: tuple[str, ...] = (
    "Cell values come from the manufacturer datasheet named in the cell's source; "
    "check the latest revision before building.",
    "Voltage sag uses a simple DC-resistance model at nominal voltage; real sag depends on "
    "state of charge, temperature and pulse length.",
    "Mass and specific energy cover the cells only; holders, nickel strip, BMS, wiring and "
    "enclosure typically add 20-40 %.",
    "Wire ampacity uses a design current density; check the wire manufacturer's rating "
    "for your insulation, bundling and ambient temperature.",
)


# --------------------------------------------------------------------------- helpers


def _runtime(hours: float | None) -> str:
    if hours is None:
        return "n/a (no load)"
    minutes = hours * 60
    return f"{minutes:.1f} min" if minutes < 120 else f"{hours:.2f} h"


def _yes_no(value: bool) -> str:
    return "yes" if value else "NO - exceeds cell rating"


@dataclass(frozen=True)
class _Section:
    title: str
    rows: list[tuple[str, str]]


def _render_sections(
    title: str, sections: Sequence[_Section], notes: Iterable[str], fmt: str
) -> str:
    lines: list[str] = []
    if fmt == "markdown":
        lines += [f"# {title}", ""]
        for section in sections:
            lines += [f"## {section.title}", "", "| Quantity | Value |", "|---|---:|"]
            lines += [f"| {label} | {value} |" for label, value in section.rows]
            lines.append("")
        lines += ["## Notes", ""]
        lines += [f"- {note}" for note in notes]
    else:
        lines += [title, "=" * len(title), ""]
        width = max((len(label) for s in sections for label, _ in s.rows), default=0) + 3
        for section in sections:
            lines.append(section.title)
            lines += [f"  {label.ljust(width)}{value}" for label, value in section.rows]
            lines.append("")
        lines.append("Notes")
        lines += [f"  - {note}" for note in notes]
    return "\n".join(lines) + "\n"


def _render_table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], right: set[int], fmt: str
) -> str:
    if fmt == "markdown":
        align = ["---:" if i in right else "---" for i in range(len(headers))]
        out = ["| " + " | ".join(headers) + " |", "|" + "|".join(align) + "|"]
        out += ["| " + " | ".join(row) + " |" for row in rows]
        return "\n".join(out)
    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))]

    def line(cells: Sequence[str]) -> str:
        parts = [
            c.rjust(widths[i]) if i in right else c.ljust(widths[i]) for i, c in enumerate(cells)
        ]
        return "  ".join(parts).rstrip()

    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)


# --------------------------------------------------------------------------- cells


def cells_dict(cells: Iterable[Cell]) -> dict[str, Any]:
    return {"cells": [cell.to_dict() for cell in cells]}


def render_cells(cells: Iterable[Cell], fmt: str) -> str:
    cell_list = list(cells)
    if not cell_list:
        return "No cells available.\n"
    headers = ["ID", "Cell", "Chem.", "Size", "V nom", "Ah", "Max A", "Wh", "Mass g"]
    rows = [
        [
            c.id,
            c.name,
            c.chemistry,
            c.form_factor,
            f"{c.nominal_voltage_v:.2f}",
            f"{c.capacity_ah:.2f}",
            f"{c.max_continuous_discharge_a:g}",
            f"{c.energy_wh:.1f}",
            f"{c.mass_kg * 1000:.1f}",
        ]
        for c in cell_list
    ]
    table = _render_table(headers, rows, right={4, 5, 6, 7, 8}, fmt=fmt)
    if fmt == "markdown":
        return f"# Cell library\n\n{table}\n"
    return f"Cell library\n============\n\n{table}\n"


# --------------------------------------------------------------------------- analysis


def analysis_dict(pack: PackConfig, load: LoadPoint, plan: ProtectionPlan | None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "configuration": pack.label,
        "cell": pack.cell.to_dict(),
        "series": pack.series,
        "parallel": pack.parallel,
        "cell_count": pack.cell_count,
        "voltage_v": {
            "min": pack.min_voltage_v,
            "nominal": pack.nominal_voltage_v,
            "max": pack.max_voltage_v,
        },
        "capacity_ah": pack.capacity_ah,
        "energy_wh": pack.energy_wh,
        "internal_resistance_ohm": pack.internal_resistance_ohm,
        "max_continuous_current_a": pack.max_continuous_current_a,
        "max_continuous_power_w": pack.max_continuous_power_w,
        "max_charge_current_a": pack.max_charge_current_a,
        "cell_mass_kg": pack.cell_mass_kg,
        "specific_energy_wh_per_kg": pack.specific_energy_wh_per_kg,
        "load": {
            "current_a": load.current_a,
            "c_rate": load.c_rate,
            "voltage_under_load_v": load.voltage_under_load_v,
            "power_w": load.power_w,
            "heat_w": load.heat_w,
            "heat_per_cell_w": load.heat_per_cell_w,
            "ideal_runtime_h": load.ideal_runtime_h,
            "within_discharge_limit": load.within_discharge_limit,
        },
        "notes": list(MODEL_NOTES),
    }
    if plan is not None:
        data["main_wiring"] = {
            "fuse_rating_a": plan.fuse_rating_a,
            "wire_awg": plan.wire.awg,
            "wire_area_mm2": plan.wire.area_mm2,
            "wire_ampacity_a": plan.wire.ampacity_a,
            "one_way_length_m": plan.wire.one_way_length_m,
            "voltage_drop_v": plan.wire.voltage_drop_v,
            "voltage_drop_fraction": plan.wire.voltage_drop_fraction,
            "power_loss_w": plan.wire.power_loss_w,
        }
    return data


def render_analysis(
    pack: PackConfig, load: LoadPoint, plan: ProtectionPlan | None, fmt: str
) -> str:
    cell = pack.cell
    sections = [
        _Section(
            "Electrical",
            [
                ("Cells", f"{pack.cell_count} ({pack.series} series x {pack.parallel} parallel)"),
                (
                    "Voltage (min / nom / max)",
                    f"{pack.min_voltage_v:.1f} / {pack.nominal_voltage_v:.1f} / "
                    f"{pack.max_voltage_v:.1f} V",
                ),
                ("Capacity", f"{pack.capacity_ah:.2f} Ah"),
                ("Energy", f"{pack.energy_wh:.1f} Wh"),
                ("Internal resistance", f"{pack.internal_resistance_ohm * 1000:.1f} mOhm (cells)"),
                ("Max continuous current", f"{pack.max_continuous_current_a:.1f} A"),
                ("Max continuous power", f"{pack.max_continuous_power_w:.0f} W"),
                ("Max charge current", f"{pack.max_charge_current_a:.1f} A"),
            ],
        ),
        _Section(
            "Mechanical",
            [
                ("Cell mass", f"{pack.cell_mass_kg:.3f} kg"),
                ("Specific energy (cells)", f"{pack.specific_energy_wh_per_kg:.0f} Wh/kg"),
            ],
        ),
        _Section(
            f"Operating point at {load.current_a:g} A ({load.c_rate:.2f}C)",
            [
                ("Voltage under load", f"{load.voltage_under_load_v:.2f} V"),
                ("Output power", f"{load.power_w:.0f} W"),
                ("Heat in cells", f"{load.heat_w:.1f} W ({load.heat_per_cell_w:.2f} W per cell)"),
                ("Ideal runtime", _runtime(load.ideal_runtime_h)),
                ("Within cell rating", _yes_no(load.within_discharge_limit)),
            ],
        ),
    ]
    if plan is not None:
        wire = plan.wire
        sections.append(
            _Section(
                f"Main wiring ({wire.one_way_length_m:g} m one-way)",
                [
                    ("Fuse", f"{plan.fuse_rating_a:g} A"),
                    (
                        "Wire",
                        f"{wire.awg} AWG ({wire.area_mm2:.2f} mm2, rated {wire.ampacity_a:.0f} A)",
                    ),
                    (
                        "Voltage drop",
                        f"{wire.voltage_drop_v:.3f} V ({wire.voltage_drop_fraction:.2%})",
                    ),
                    ("Wire loss", f"{wire.power_loss_w:.2f} W"),
                ],
            )
        )
    title = f"Battery pack {pack.label}: {cell.name} ({cell.chemistry}, {cell.form_factor})"
    return _render_sections(title, sections, MODEL_NOTES, fmt)


# --------------------------------------------------------------------------- design


def design_dict(result: DesignResult, top: int | None = None) -> dict[str, Any]:
    candidates = result.candidates if top is None else result.candidates[:top]
    return {
        "requirements": result.requirements.describe(),
        "candidates": [
            {
                "rank": rank,
                "cell_id": c.pack.cell.id,
                "cell": c.pack.cell.name,
                "configuration": c.pack.label,
                "cell_count": c.pack.cell_count,
                "nominal_voltage_v": c.pack.nominal_voltage_v,
                "max_voltage_v": c.pack.max_voltage_v,
                "capacity_ah": c.pack.capacity_ah,
                "energy_wh": c.pack.energy_wh,
                "max_continuous_current_a": c.pack.max_continuous_current_a,
                "cell_mass_kg": c.pack.cell_mass_kg,
                "limiting_factor": c.limiting_factor,
            }
            for rank, c in enumerate(candidates, start=1)
        ],
        "rejected": [{"cell_id": r.cell.id, "reason": r.reason} for r in result.rejections],
    }


def render_design(
    result: DesignResult, fmt: str, top: int | None = None, show_rejected: bool = False
) -> str:
    candidates = result.candidates if top is None else result.candidates[:top]
    title = f"Pack design: {result.requirements.describe()}"
    out: list[str] = [f"# {title}", ""] if fmt == "markdown" else [title, "=" * len(title), ""]
    if candidates:
        headers = [
            "#",
            "Cell",
            "Config",
            "Cells",
            "V nom",
            "V max",
            "Ah",
            "Wh",
            "Max A",
            "Mass kg",
            "Sized by",
        ]
        rows = [
            [
                str(rank),
                c.pack.cell.name,
                c.pack.label,
                str(c.pack.cell_count),
                f"{c.pack.nominal_voltage_v:.1f}",
                f"{c.pack.max_voltage_v:.1f}",
                f"{c.pack.capacity_ah:.1f}",
                f"{c.pack.energy_wh:.0f}",
                f"{c.pack.max_continuous_current_a:.0f}",
                f"{c.pack.cell_mass_kg:.2f}",
                c.limiting_factor,
            ]
            for rank, c in enumerate(candidates, start=1)
        ]
        out.append(_render_table(headers, rows, right={0, 3, 4, 5, 6, 7, 8, 9}, fmt=fmt))
        hidden = len(result.candidates) - len(candidates)
        if hidden > 0:
            out += ["", f"({hidden} more feasible design(s) not shown; use --top to see more)"]
    else:
        out.append("No cell meets these requirements.")
    if result.rejections and (show_rejected or not candidates):
        out += ["", "## Rejected" if fmt == "markdown" else "Rejected", ""]
        bullet = "-" if fmt == "markdown" else "  -"
        out += [f"{bullet} {r.cell.name}: {r.reason}" for r in result.rejections]
    elif result.rejections:
        out += ["", f"{len(result.rejections)} cell(s) rejected; use --show-rejected for reasons."]
    return "\n".join(out) + "\n"
