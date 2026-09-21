"""Write the footprints and symbols into ``parts/``.

    python tools/build_parts.py

Each part gets a directory ato can point at with ``is_atomic_part``.  The
switch footprint is checked as it is written: it carries two switch standards
and a hotswap socket on one 19mm pitch, and the only thing keeping the poles
apart is 0.17mm of laminate, so a change that closes that gap should fail here
rather than at the fab.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from footprints import (  # noqa: E402
    MODELUD_LEFT, MODELUD_RIGHT, MODELUD_SIZE, PICO_PINS, PICO_SIZE,
    clearances, key_switch_pads, modelud_pads, pico_pads, render, symbol,
)

PARTS = pathlib.Path(__file__).parent.parent / "parts"

#: The switch body, which is what the outline and courtyard should show: an MX
#: is 15.6mm across the base and a Choc is 15mm.  Drawing the 19.05mm key
#: pitch instead makes every footprint claim more room than the part needs,
#: and the thumb cluster on this layout sits at 18.5mm -- close enough that
#: KiCad called it a courtyard overlap on parts that physically clear by
#: 2.4mm.
SWITCH_BODY = (15.6, 15.6)

#: The narrowest a 2-layer fab will hold reliably.  The switch footprint lands
#: at 0.17mm, so this is a real bound, not a formality.
MIN_CLEARANCE = 0.15


def write(name: str, description: str, pads, pins, outline=None) -> None:
    directory = PARTS / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.kicad_mod").write_text(
        render(name, description, pads, outline))
    (directory / f"{name}.kicad_sym").write_text(symbol(name, pins))
    print(f"  {name}: {len(pads)} pads, {len(pins)} pins")


def check(name: str, pads) -> float:
    """Tightest gap between copper on different nets."""
    gaps = [(gap, label) for gap, label in clearances(pads) if "NETS DIFFER" in label]
    if not gaps:
        return float("inf")
    worst, label = gaps[0]
    print(f"  {name}: tightest different-net gap {worst:+.3f}mm ({label.split(': ')[1]})")
    if worst < MIN_CLEARANCE:
        raise SystemExit(
            f"{name}: {worst:.3f}mm between different nets is under the "
            f"{MIN_CLEARANCE}mm this board is drawn to")
    return worst


def main() -> int:
    print("footprints:")
    switch = key_switch_pads()
    write("MakoKeySwitch",
          "Compound key switch: Kailh Choc v1 hotswap or soldered, "
          "Cherry MX soldered. Poles A and B.",
          switch, ["A", "B"], outline=SWITCH_BODY)
    write("RaspberryPiPico",
          "Raspberry Pi Pico, mounted under the board on headers or flat.",
          pico_pads(), sorted(set(PICO_PINS)), outline=PICO_SIZE)
    write("ModelUD",
          "Model UD / Model BirdD USB-C breakout, header side.",
          modelud_pads(), MODELUD_LEFT + MODELUD_RIGHT, outline=MODELUD_SIZE)

    print("clearance:")
    check("MakoKeySwitch", switch)
    check("ModelUD", modelud_pads())
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
