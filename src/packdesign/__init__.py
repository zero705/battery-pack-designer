"""Battery Pack Designer.

Size and analyse series/parallel lithium-ion battery packs from cell datasheet values.

Typical use::

    from packdesign import CellLibrary, PackConfig

    cell = CellLibrary.builtin().get("samsung-30q")
    pack = PackConfig(cell, series=8, parallel=2)
    print(pack.energy_wh)  # 172.8
"""

from packdesign.cells import Cell, CellLibrary, UnknownCellError
from packdesign.design import Candidate, DesignResult, Rejection, Requirements, design_packs
from packdesign.pack import LoadPoint, PackConfig
from packdesign.wiring import (
    ProtectionPlan,
    WireSelection,
    plan_main_wiring,
    select_fuse,
    select_wire,
)

__version__ = "0.1.0"

__all__ = [
    "Candidate",
    "Cell",
    "CellLibrary",
    "DesignResult",
    "LoadPoint",
    "PackConfig",
    "ProtectionPlan",
    "Rejection",
    "Requirements",
    "UnknownCellError",
    "WireSelection",
    "__version__",
    "design_packs",
    "plan_main_wiring",
    "select_fuse",
    "select_wire",
]
