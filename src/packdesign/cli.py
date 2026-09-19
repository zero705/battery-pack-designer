"""Command-line interface: ``packdesign cells | analyze | design | plot``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from packdesign import __version__
from packdesign.cells import CHEMISTRIES, CellLibrary, UnknownCellError
from packdesign.design import SORT_KEYS, Requirements, design_packs
from packdesign.pack import PackConfig
from packdesign.plots import (
    THEMES,
    PlottingUnavailableError,
    load_sweep,
    plot_load,
    plot_tradeoff,
    tradeoff_sweep,
)
from packdesign.report import (
    FORMATS,
    analysis_dict,
    cells_dict,
    design_dict,
    render_analysis,
    render_cells,
    render_design,
)
from packdesign.wiring import (
    DEFAULT_CURRENT_DENSITY_A_PER_MM2,
    DEFAULT_MAX_DROP_FRACTION,
    plan_main_wiring,
)

PROG = "packdesign"


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not value > 0 or value == float("inf"):
        raise argparse.ArgumentTypeError(f"must be a positive number, got {text!r}")
    return value


def _non_negative_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not value >= 0 or value == float("inf"):
        raise argparse.ArgumentTypeError(f"must be a number >= 0, got {text!r}")
    return value


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {text!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Size and analyse series/parallel lithium-ion battery packs.",
        epilog="Example: packdesign analyze --cell samsung-30q --series 8 --parallel 2",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--cells-file",
        metavar="PATH",
        help="JSON file with extra cells; they override built-in cells with the same id",
    )
    common.add_argument("--format", choices=FORMATS, default="text", help="output format")

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("cells", parents=[common], help="list available cells")

    analyze = sub.add_parser("analyze", parents=[common], help="analyse a given SxP configuration")
    analyze.add_argument("--cell", required=True, help="cell id (see 'packdesign cells')")
    analyze.add_argument(
        "-s", "--series", type=_positive_int, required=True, help="cells in series"
    )
    analyze.add_argument(
        "-p", "--parallel", type=_positive_int, required=True, help="cells in parallel"
    )
    analyze.add_argument(
        "--load",
        type=_non_negative_float,
        metavar="AMPS",
        help="load current for the operating point (default: max continuous current)",
    )
    analyze.add_argument(
        "--wire-length",
        type=_positive_float,
        default=0.5,
        metavar="M",
        help="one-way main cable length in metres (default: 0.5)",
    )
    analyze.add_argument(
        "--max-drop",
        type=_positive_float,
        default=DEFAULT_MAX_DROP_FRACTION * 100,
        metavar="PERCENT",
        help="allowed voltage drop in the main cable, in %% (default: 2)",
    )
    analyze.add_argument(
        "--current-density",
        type=_positive_float,
        default=DEFAULT_CURRENT_DENSITY_A_PER_MM2,
        metavar="A_PER_MM2",
        help="wire design current density (default: 8)",
    )

    design = sub.add_parser("design", parents=[common], help="find packs that meet requirements")
    target = design.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--voltage", type=_positive_float, metavar="V", help="target nominal voltage"
    )
    target.add_argument("--series", type=_positive_int, metavar="N", help="fixed series count")
    size = design.add_mutually_exclusive_group()
    size.add_argument("--energy", type=_positive_float, metavar="WH", help="minimum energy")
    size.add_argument("--capacity", type=_positive_float, metavar="AH", help="minimum capacity")
    design.add_argument(
        "--current",
        type=_non_negative_float,
        default=0.0,
        metavar="A",
        help="continuous discharge current",
    )
    design.add_argument(
        "--charge-current",
        type=_non_negative_float,
        default=0.0,
        metavar="A",
        help="charge current",
    )
    design.add_argument("--max-mass", type=_positive_float, metavar="KG", help="maximum cell mass")
    design.add_argument(
        "--max-voltage", type=_positive_float, metavar="V", help="maximum full-charge voltage"
    )
    design.add_argument("--chemistry", choices=CHEMISTRIES, help="only consider this chemistry")
    design.add_argument("--sort", choices=SORT_KEYS, default="mass", help="ranking (default: mass)")
    design.add_argument(
        "--top", type=_positive_int, default=5, metavar="N", help="designs to show (default: 5)"
    )
    design.add_argument("--show-rejected", action="store_true", help="explain rejected cells")

    _add_plot_parser(sub)
    return parser


def _add_plot_parser(sub: Any) -> None:
    chart_common = argparse.ArgumentParser(add_help=False)
    chart_common.add_argument(
        "--cells-file",
        metavar="PATH",
        help="JSON file with extra cells; they override built-in cells with the same id",
    )
    chart_common.add_argument(
        "-o", "--output", required=True, metavar="FILE", help="image file (.png, .svg or .pdf)"
    )
    chart_common.add_argument("--theme", choices=THEMES, default="light", help="colour theme")

    plot = sub.add_parser("plot", help="draw charts (needs the optional matplotlib dependency)")
    charts = plot.add_subparsers(dest="chart", required=True, metavar="CHART")

    load = charts.add_parser(
        "load", parents=[chart_common], help="voltage and heat per cell versus load current"
    )
    load.add_argument("--cell", required=True, help="cell id (see 'packdesign cells')")
    load.add_argument("-s", "--series", type=_positive_int, required=True, help="cells in series")
    load.add_argument(
        "-p", "--parallel", type=_positive_int, required=True, help="cells in parallel"
    )
    load.add_argument(
        "--max-load",
        type=_positive_float,
        metavar="AMPS",
        help="right end of the current axis (default: 1.5 x rated current)",
    )

    tradeoff = charts.add_parser(
        "tradeoff", parents=[chart_common], help="lightest pack per cell as current rises"
    )
    target = tradeoff.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--voltage", type=_positive_float, metavar="V", help="target nominal voltage"
    )
    target.add_argument("--series", type=_positive_int, metavar="N", help="fixed series count")
    size = tradeoff.add_mutually_exclusive_group(required=True)
    size.add_argument("--energy", type=_positive_float, metavar="WH", help="minimum energy")
    size.add_argument("--capacity", type=_positive_float, metavar="AH", help="minimum capacity")
    tradeoff.add_argument(
        "--max-current",
        type=_positive_float,
        default=100.0,
        metavar="A",
        help="right end of the current axis (default: 100)",
    )
    tradeoff.add_argument(
        "--max-voltage", type=_positive_float, metavar="V", help="maximum full-charge voltage"
    )
    tradeoff.add_argument(
        "--max-mass", type=_positive_float, metavar="KG", help="maximum cell mass"
    )
    tradeoff.add_argument("--chemistry", choices=CHEMISTRIES, help="only consider this chemistry")
    tradeoff.add_argument(
        "--highlight",
        nargs="+",
        default=[],
        metavar="CELL",
        help="cell ids to label at the end of their line",
    )


def _load_library(cells_file: str | None) -> CellLibrary:
    library = CellLibrary.builtin()
    if cells_file:
        library = library.merged(CellLibrary.from_json_file(cells_file))
    return library


def _emit(fmt: str, text: str, data: dict[str, Any]) -> None:
    if fmt == "json":
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
    else:
        sys.stdout.write(text)


def _run_plot(args: argparse.Namespace, library: CellLibrary) -> None:
    if args.chart == "load":
        pack = PackConfig(library.get(args.cell), args.series, args.parallel)
        path = plot_load(load_sweep(pack, args.max_load), args.output, theme=args.theme)
    else:
        for cell_id in args.highlight:
            library.get(cell_id)  # fail early on a typo
        req = Requirements(
            nominal_voltage_v=args.voltage,
            series=args.series,
            energy_wh=args.energy,
            capacity_ah=args.capacity,
            max_voltage_v=args.max_voltage,
            max_mass_kg=args.max_mass,
            chemistry=args.chemistry,
        )
        data = tradeoff_sweep(library, req, args.max_current)
        path = plot_tradeoff(data, args.output, theme=args.theme, highlight=args.highlight)
    sys.stdout.write(f"Saved {path}\n")


def _run(args: argparse.Namespace) -> None:
    library = _load_library(args.cells_file)
    if args.command == "plot":
        _run_plot(args, library)
        return
    fmt: str = args.format

    if args.command == "cells":
        _emit(fmt, render_cells(library, fmt) if fmt != "json" else "", cells_dict(library))
        return

    if args.command == "analyze":
        pack = PackConfig(library.get(args.cell), args.series, args.parallel)
        current = pack.max_continuous_current_a if args.load is None else args.load
        load = pack.at_load(current)
        plan = None
        if current > 0:
            plan = plan_main_wiring(
                current,
                args.wire_length,
                pack.nominal_voltage_v,
                max_drop_fraction=args.max_drop / 100,
                current_density_a_per_mm2=args.current_density,
            )
        text = render_analysis(pack, load, plan, fmt) if fmt != "json" else ""
        _emit(fmt, text, analysis_dict(pack, load, plan))
        return

    req = Requirements(
        nominal_voltage_v=args.voltage,
        series=args.series,
        energy_wh=args.energy,
        capacity_ah=args.capacity,
        continuous_current_a=args.current,
        charge_current_a=args.charge_current,
        max_mass_kg=args.max_mass,
        max_voltage_v=args.max_voltage,
        chemistry=args.chemistry,
    )
    result = design_packs(library, req, sort_by=args.sort)
    text = (
        render_design(result, fmt, top=args.top, show_rejected=args.show_rejected)
        if fmt != "json"
        else ""
    )
    _emit(fmt, text, design_dict(result, top=args.top))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code (0 = success, 1 = error, 2 = usage)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _run(args)
    except (ValueError, UnknownCellError, OSError, PlottingUnavailableError) as exc:
        sys.stderr.write(f"{PROG}: error: {exc}\n")
        return 1
    return 0
