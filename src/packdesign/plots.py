"""Charts: pack behaviour under load, and the cell trade-off as current rises.

The sweep functions are pure Python and always available. Rendering needs the
optional ``matplotlib`` dependency (``pip install "battery-pack-designer[plot]"``);
it is imported only when a chart is drawn.

Colours come from a categorical palette validated for colour-vision deficiency in
both themes; each cell keeps its colour by its position in the cell list, so
filtering never repaints the survivors.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packdesign.cells import Cell
from packdesign.design import Candidate, Requirements, size_pack
from packdesign.pack import PackConfig

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

THEMES: tuple[str, ...] = ("light", "dark")
MAX_SERIES = 8


class PlottingUnavailableError(RuntimeError):
    """Raised when a chart is requested but matplotlib is not installed."""


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class LoadSweep:
    """Terminal voltage and heat per cell across a range of load currents."""

    pack: PackConfig
    currents_a: list[float]
    voltages_v: list[float]
    heat_per_cell_w: list[float]


@dataclass(frozen=True)
class TradeoffSeries:
    """Cell mass of the best pack for one cell at each current (None = infeasible)."""

    cell: Cell
    masses_kg: list[float | None]
    labels: list[str | None]


@dataclass(frozen=True)
class Tradeoff:
    requirements: Requirements
    currents_a: list[float]
    series: list[TradeoffSeries]


def load_sweep(
    pack: PackConfig, max_current_a: float | None = None, points: int = 241
) -> LoadSweep:
    """Sample the pack from 0 A to ``max_current_a`` (default 1.5 x rated current).

    The range is capped at 95 % of the current where the resistance model would
    predict 0 V, because the model is meaningless beyond that point.
    """
    if points < 2:
        raise ValueError("points must be at least 2")
    limit = 1.5 * pack.max_continuous_current_a if max_current_a is None else max_current_a
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError(f"max_current_a must be a positive number, got {max_current_a!r}")
    limit = min(limit, 0.95 * pack.nominal_voltage_v / pack.internal_resistance_ohm)
    currents = [limit * i / (points - 1) for i in range(points)]
    loads = [pack.at_load(current) for current in currents]
    return LoadSweep(
        pack=pack,
        currents_a=currents,
        voltages_v=[load.voltage_under_load_v for load in loads],
        heat_per_cell_w=[load.heat_per_cell_w for load in loads],
    )


def tradeoff_sweep(
    cells: Iterable[Cell], requirements: Requirements, max_current_a: float, step_a: float = 1.0
) -> Tradeoff:
    """Size a pack for every cell at each current from 0 A to ``max_current_a``.

    ``requirements.continuous_current_a`` is replaced by the swept current; all other
    requirements (voltage, energy, limits) stay as given.
    """
    if not math.isfinite(max_current_a) or max_current_a <= 0:
        raise ValueError(f"max_current_a must be a positive number, got {max_current_a!r}")
    if not math.isfinite(step_a) or step_a <= 0:
        raise ValueError(f"step_a must be a positive number, got {step_a!r}")
    cell_list = list(cells)
    if not cell_list:
        raise ValueError("no cells to compare")
    if len(cell_list) > MAX_SERIES:
        raise ValueError(
            f"at most {MAX_SERIES} cells can be compared in one chart "
            f"(got {len(cell_list)}); filter with --chemistry or a smaller cells file"
        )
    count = math.floor(max_current_a / step_a + 1e-9)
    currents = [i * step_a for i in range(count + 1)]
    series = []
    for cell in cell_list:
        masses: list[float | None] = []
        labels: list[str | None] = []
        for current in currents:
            outcome = size_pack(cell, replace(requirements, continuous_current_a=current))
            if isinstance(outcome, Candidate):
                masses.append(outcome.pack.cell_mass_kg)
                labels.append(outcome.pack.label)
            else:
                masses.append(None)
                labels.append(None)
        series.append(TradeoffSeries(cell, masses, labels))
    return Tradeoff(requirements, currents, series)


# --------------------------------------------------------------------------- styling


@dataclass(frozen=True)
class _Theme:
    surface: str
    ink: str
    ink_secondary: str
    muted: str
    grid: str
    axis: str
    wash: str
    series: tuple[str, ...]


_THEMES: dict[str, _Theme] = {
    "light": _Theme(
        surface="#fcfcfb",
        ink="#0b0b0b",
        ink_secondary="#52514e",
        muted="#898781",
        grid="#e1e0d9",
        axis="#c3c2b7",
        wash="#f0efec",
        series=(
            "#2a78d6",
            "#eb6834",
            "#1baf7a",
            "#eda100",
            "#e87ba4",
            "#008300",
            "#4a3aa7",
            "#e34948",
        ),
    ),
    "dark": _Theme(
        surface="#1a1a19",
        ink="#ffffff",
        ink_secondary="#c3c2b7",
        muted="#898781",
        grid="#2c2c2a",
        axis="#383835",
        wash="#262625",
        series=(
            "#3987e5",
            "#d95926",
            "#199e70",
            "#c98500",
            "#d55181",
            "#008300",
            "#9085e9",
            "#e66767",
        ),
    ),
}

_FONT = ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]


def _theme(name: str) -> _Theme:
    try:
        return _THEMES[name]
    except KeyError:
        raise ValueError(f"theme must be one of: {', '.join(THEMES)}") from None


def _new_figure(width: float, height: float, theme: _Theme) -> Figure:
    try:
        import matplotlib  # noqa: PLC0415 - optional dependency, imported on demand
        from matplotlib.figure import Figure  # noqa: PLC0415
    except ImportError:
        raise PlottingUnavailableError(
            'charts need matplotlib: python -m pip install "battery-pack-designer[plot]"'
        ) from None
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = _FONT
    matplotlib.rcParams["svg.fonttype"] = "none"
    return Figure(figsize=(width, height), dpi=100, facecolor=theme.surface)


def _style_axes(ax: Axes, theme: _Theme) -> None:
    ax.set_facecolor(theme.surface)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(theme.axis)
    ax.spines["bottom"].set_linewidth(1)
    ax.grid(axis="y", color=theme.grid, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=theme.muted, labelcolor=theme.ink_secondary, labelsize=9, length=0, pad=6)
    ax.xaxis.label.set_color(theme.ink_secondary)
    ax.yaxis.label.set_color(theme.ink_secondary)


def _titles(fig: Figure, theme: _Theme, title: str, subtitle: str) -> None:
    fig.text(0.02, 0.955, title, color=theme.ink, fontsize=13.5, fontweight="semibold", va="top")
    fig.text(0.02, 0.885, subtitle, color=theme.ink_secondary, fontsize=9.5, va="top")


def _save(fig: Figure, path: str | Path) -> Path:
    out = Path(path)
    if out.parent and not out.parent.exists():
        raise OSError(f"folder does not exist: {out.parent}")
    fig.savefig(out, dpi=200, facecolor=fig.get_facecolor())
    return out


def _pretty(text: str) -> str:
    return text.replace(">=", "≥").replace("<=", "≤")


def _end_dot(ax: Axes, x: float, y: float, colour: str, theme: _Theme) -> None:
    ax.scatter(
        [x],
        [y],
        s=46,
        color=colour,
        edgecolors=theme.surface,
        linewidths=2,
        zorder=5,
        clip_on=False,
    )


# --------------------------------------------------------------------------- charts


def plot_load(sweep: LoadSweep, path: str | Path, theme: str = "light") -> Path:
    """Two panels sharing the current axis: terminal voltage and heat per cell."""
    t = _theme(theme)
    pack = sweep.pack
    fig = _new_figure(9.6, 4.6, t)
    _titles(
        fig,
        t,
        f"{pack.label} {pack.cell.name} under load",
        f"Resistance model with {pack.cell.internal_resistance_ohm * 1000:g} mOhm per cell. "
        f"Shaded: above the rated {pack.max_continuous_current_a:g} A.",
    )
    axes = fig.subplots(1, 2, gridspec_kw={"wspace": 0.28})
    fig.subplots_adjust(left=0.07, right=0.97, top=0.74, bottom=0.14)
    rated = pack.max_continuous_current_a
    x_max = sweep.currents_a[-1]
    at_rated = pack.at_load(rated) if rated <= x_max else None
    colour = t.series[0]
    panels: Sequence[tuple[Axes, list[float], str, str]] = (
        (axes[0], sweep.voltages_v, "Terminal voltage (V)", "V"),
        (axes[1], sweep.heat_per_cell_w, "Heat per cell (W)", "W"),
    )
    for ax, values, label, unit in panels:
        _style_axes(ax, t)
        if rated < x_max:
            ax.axvspan(rated, x_max, color=t.wash, zorder=0, linewidth=0)
        ax.plot(sweep.currents_a, values, color=colour, linewidth=2, solid_capstyle="round")
        ax.set_xlim(0, x_max)
        ax.set_xlabel("Load current (A)", fontsize=9.5)
        ax.set_title(label, loc="left", color=t.ink, fontsize=10.5, pad=10)
        if at_rated is not None:
            y = at_rated.voltage_under_load_v if unit == "V" else at_rated.heat_per_cell_w
            _end_dot(ax, rated, y, colour, t)
            ax.annotate(
                f"{rated:g} A: {y:.2f} {unit}",
                (rated, y),
                xytext=(-8, 10),
                textcoords="offset points",
                ha="right",
                color=t.ink,
                fontsize=9,
            )
    volt_ax = axes[0]
    volt_ax.set_ylim(0, pack.max_voltage_v * 1.08)
    volt_ax.axhline(pack.min_voltage_v, color=t.muted, linewidth=1)
    volt_ax.annotate(
        f"cut-off {pack.min_voltage_v:.1f} V",
        (x_max, pack.min_voltage_v),
        xytext=(-6, -13),
        textcoords="offset points",
        ha="right",
        color=t.ink_secondary,
        fontsize=8.5,
    )
    axes[1].set_ylim(0, max(sweep.heat_per_cell_w) * 1.1)
    return _save(fig, path)


def plot_tradeoff(
    data: Tradeoff, path: str | Path, theme: str = "light", highlight: Sequence[str] = ()
) -> Path:
    """Cell mass of the best pack for each cell as the current requirement rises."""
    t = _theme(theme)
    if all(m is None for line in data.series for m in line.masses_kg):
        raise ValueError("no cell meets these requirements at any current; nothing to plot")
    fig = _new_figure(9.6, 5.6, t)
    _titles(
        fig,
        t,
        f"Lightest pack per cell for {_pretty(data.requirements.describe())}",
        "Cell mass of the smallest pack that meets the requirements at each continuous current. "
        "Each step adds one cell in parallel.",
    )
    ax = fig.add_subplot(1, 1, 1)
    fig.subplots_adjust(left=0.07, right=0.84, top=0.72, bottom=0.11)
    _style_axes(ax, t)
    x_end = data.currents_a[-1]
    y_top = 0.0
    handles: list[Any] = []
    for index, line in enumerate(data.series):
        colour = t.series[index]
        ys = [math.nan if m is None else m for m in line.masses_kg]
        finite = [y for y in ys if not math.isnan(y)]
        if not finite:  # e.g. filtered out by chemistry; its colour slot stays reserved
            continue
        (handle,) = ax.plot(
            data.currents_a,
            ys,
            color=colour,
            linewidth=2,
            drawstyle="steps-post",
            solid_joinstyle="miter",
            label=line.cell.name,
            zorder=3 if line.cell.id in highlight else 2,  # highlighted lines stay on top
        )
        handles.append(handle)
        y_top = max(y_top, *finite)
        last = line.masses_kg[-1]
        if last is not None:
            _end_dot(ax, x_end, last, colour, t)
            if line.cell.id in highlight:
                ax.annotate(
                    f"{line.cell.name}\n{line.labels[-1]}, {last:.2f} kg",
                    (x_end, last),
                    xytext=(10, 0),
                    textcoords="offset points",
                    va="center",
                    color=t.ink,
                    fontsize=8.5,
                    annotation_clip=False,
                )
    ax.set_xlim(0, x_end)
    ax.set_ylim(0, y_top * 1.08)
    ax.set_xlabel("Required continuous discharge current (A)", fontsize=9.5)
    ax.set_ylabel("Cell mass (kg)", fontsize=9.5)
    legend = fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.02, 0.83),
        ncol=min(len(handles), 3),
        frameon=False,
        fontsize=9,
        handlelength=1.6,
        columnspacing=1.6,
    )
    for text in legend.get_texts():
        text.set_color(t.ink_secondary)
    return _save(fig, path)
