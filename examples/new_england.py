"""New England states mobile.

Structure (top to bottom):
  - Top arc: everything else (left) balanced by ME (right)
  - Mid arc: VT+NH (left), CT+RI+MA (right)
  - CT+RI arc balanced by MA
"""

from pathlib import Path
from mbl import Arc, Leaf, Mobile, MobileConfig

# State SVG paths
states = Path("mbl") / "assets" / "states"
ME = Leaf.from_svg(str(states / "ME.svg"))
NH = Leaf.from_svg(str(states / "NH.svg"))
VT = Leaf.from_svg(str(states / "VT.svg"))
MA = Leaf.from_svg(str(states / "MA.svg"))
CT = Leaf.from_svg(str(states / "CT.svg"))
RI = Leaf.from_svg(str(states / "RI.svg"))

s = 0.17

mobile = Mobile(
    [
        # Row 0: hole on left, ME on right
        Arc(100, 22) @ (None, ME * s),
        # Row 1: connector — VT+NH hole (left), CT+RI/MA hole (right)
        Arc(90, 18) @ (None, None),
        # Row 2: VT+NH arc (left fills row1 left), MA+CT/RI arc (right fills row1 right)
        [
            Arc(45, 12) @ (VT * s, NH * s),
            Arc(50, 10) @ (None, MA * s),
        ],
        # Row 3: CT+RI fills the hole in the MA arc
        Arc(35, 10) @ (CT * s, RI * s),
    ],
    config=MobileConfig(),
)

if __name__ == "__main__":
    out = mobile.to_3mf("new-england.3mf")
    print(f"Generated {out}")
