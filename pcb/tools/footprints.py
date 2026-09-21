"""Generate the KiCad footprints this board needs.

Three of them are not in any stock library, so they are built here rather than
copied in: the compound key switch, the Pico as a bottom-mounted module, and
the Model UD's header pair.  Generating them means the numbers live in one
place, next to the clearance checks that say whether they can coexist -- which
for the switch is the whole question, because it has to take two switch
standards and a hotswap socket on the same 19mm of board.

Dimensions come from the Cherry MX and Kailh Choc/PG1350 drawings, cross
checked against the footprints in daprice/keyswitches.pretty (CC BY-SA 4.0).
Run ``python tools/footprints.py`` to write them into ``parts/``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

MM = 1.0


@dataclass(frozen=True)
class Pad:
    """One pad, hole or piece of copper in a footprint."""

    name: str
    x: float
    y: float
    #: Copper size; a circle when only ``size`` is given.
    size: float
    height: float = None
    #: Hole diameter.  0 for surface mount.
    drill: float = 0.0
    plated: bool = True
    layers: tuple[str, ...] = ("*.Cu", "*.Mask")
    shape: str = "circle"
    #: What this is for, in the silkscreen-free sense: shows up in the report.
    note: str = ""

    @property
    def width(self) -> float:
        return self.size

    def extent(self) -> float:
        """Radius of the copper, for clearance sums."""
        return max(self.size, self.height or self.size) / 2

    def render(self) -> str:
        kind = "thru_hole" if self.drill and self.plated else (
            "np_thru_hole" if self.drill else "smd")
        size = f"{self.size} {self.height or self.size}"
        drill = f" (drill {self.drill})" if self.drill else ""
        layers = " ".join(f'"{layer}"' for layer in self.layers)
        name = f'"{self.name}"'
        return (f'  (pad {name} {kind} {self.shape} (at {self.x:.4g} {self.y:.4g}) '
                f'(size {size}){drill} (layers {layers}))')


# --- Cherry MX, top view, pins below centre --------------------------------
MX_CENTRE = 4.0
MX_LEG = 5.08
MX_LEG_HOLE = 1.7
MX_PINS = {"1": (-3.81, 2.54), "2": (2.54, 5.08)}
MX_PIN_DRILL = 1.5
#: Trimmed to the smallest ring a 2-layer fab will hold (0.2mm), because the
#: only thing this pad has to clear is Choc pin 2, 2.77mm away.
MX_PIN_PAD = 1.8

# --- Kailh Choc v1 (PG1350), same convention -------------------------------
CHOC_CENTRE = 3.4
CHOC_LEG = 5.5
CHOC_PINS = {"1": (0.0, 5.9), "2": (5.0, 3.8)}
#: The socket's barrels sit in these, so they are far wider than a switch pin
#: needs.  A pin soldered straight in gets the annular ring instead.
CHOC_SOCKET_HOLE = 3.0
CHOC_SOCKET_PAD = (2.6, 2.6)
#: How far the socket's copper reaches out from its barrel.
CHOC_SOCKET_REACH = 3.275
#: Likewise trimmed: 0.15mm of ring on a 3.0mm hole.  A wider ring shorts to
#: Pad round the MX pin.  1.8 rather than 1.9: at 1.9 it comes within 0.17mm
#: of the Choc socket pad beside it, which is under the 0.2mm a 2-layer fab
#: will hold, and DRC says so.  0.15mm of annular ring is still enough for a
#: plated through hole.
#:
#: MX pin 2, which is what the clearance check is there to catch.
CHOC_PIN_PAD = 3.3

#: Poles are paired across the two standards so that the two holes that end up
#: closest together -- MX pin 2 and Choc pin 1, 2.67mm apart -- are the same
#: net and may overlap.  The other pairing leaves them on opposite poles and
#: the footprint will not clear.
POLE = {"A": ("MX 1", "CHOC 2"), "B": ("MX 2", "CHOC 1")}


def key_switch_pads() -> list[Pad]:
    """Every hole and pad in the compound switch footprint."""
    pads: list[Pad] = []

    # Stem clearance: the larger of the two, so either switch drops in.
    pads.append(Pad("", 0, 0, MX_CENTRE, drill=MX_CENTRE, plated=False,
                    note="stem, MX 4.0 over Choc 3.4"))

    # The two standards' locating legs are 0.42mm apart, which is closer than
    # two holes can sit -- so they become one slot each side.
    span = CHOC_LEG - MX_LEG
    for side in (-1, 1):
        pads.append(Pad("", side * (MX_LEG + span / 2), 0,
                        MX_LEG_HOLE + span, MX_LEG_HOLE, drill=MX_LEG_HOLE,
                        plated=False, shape="oval",
                        note=f"locating leg, MX {MX_LEG} and Choc {CHOC_LEG}"))

    pole_of = {pin: pole for pole, pins in POLE.items() for pin in pins}

    # Choc pins carry the hotswap socket, so they are the wide plated holes.
    for pin, (x, y) in CHOC_PINS.items():
        pads.append(Pad(pole_of[f"CHOC {pin}"], x, y, CHOC_PIN_PAD,
                        drill=CHOC_SOCKET_HOLE,
                        note=f"Choc pin {pin} / socket barrel"))

    # MX pins are solder-only: an MX socket will not fit beside a Choc one.
    for pin, (x, y) in MX_PINS.items():
        pads.append(Pad(pole_of[f"MX {pin}"], x, y, MX_PIN_PAD, drill=MX_PIN_DRILL,
                        note=f"MX pin {pin}, solder only"))

    # Socket copper, on the back where the socket lives.
    for pin, (x, y) in CHOC_PINS.items():
        reach = -CHOC_SOCKET_REACH if pin == "1" else CHOC_SOCKET_REACH
        pads.append(Pad(pole_of[f"CHOC {pin}"], x + reach, y,
                        *CHOC_SOCKET_PAD, shape="rect",
                        layers=("B.Cu", "B.Paste", "B.Mask"),
                        note=f"Choc hotswap socket, pin {pin}"))
    return pads


def clearances(pads: list[Pad]) -> list[tuple[float, str]]:
    """Gap between every pair of pads that are not the same net.

    Same-net copper may overlap; different nets may not.  This is what decides
    whether two switch standards fit in one footprint at all.
    """
    report = []
    for i, a in enumerate(pads):
        for b in pads[i + 1:]:
            same_net = a.name and a.name == b.name
            back = "B.Cu" in a.layers
            if back != ("B.Cu" in b.layers):
                continue  # different sides, no clearance to keep
            gap = math.dist((a.x, a.y), (b.x, b.y)) - a.extent() - b.extent()
            label = f"{a.note or a.name} <-> {b.note or b.name}"
            report.append((gap, f"{'same net' if same_net else 'NETS DIFFER'}: {label}"))
    return sorted(report)


# --- Raspberry Pi Pico, mounted under the board ----------------------------
PICO_SIZE = (21.0, 51.0)
PICO_ROW = 17.78 / 2
PICO_PITCH = 2.54
PICO_FIRST_Y = -24.13
PICO_DRILL = 1.02
PICO_PAD = 1.7

#: Physical pin to signal, straight off the Pico pinout: 1-20 down the left,
#: 21-40 up the right.  Pads are named by signal rather than numbered, so the
#: ato side can say ``pico.package.GP4`` instead of counting pins -- and the
#: eight GND pads collapse onto one symbol pin, which is what you want.
#: Names avoid leading digits and punctuation so they are valid identifiers.
PICO_PINS = [
    "GP0", "GP1", "GND", "GP2", "GP3", "GP4", "GP5", "GND", "GP6", "GP7",
    "GP8", "GP9", "GND", "GP10", "GP11", "GP12", "GP13", "GND", "GP14", "GP15",
    "GP16", "GP17", "GND", "GP18", "GP19", "GP20", "GP21", "GND", "GP22", "RUN",
    "GP26", "GP27", "AGND", "GP28", "VREF", "V3V3", "V3V3_EN", "GND", "VSYS", "VBUS",
]


def pico_pads() -> list[Pad]:
    """Plated holes, so the Pico can sit on headers or be soldered flat."""
    pads = []
    for index, name in enumerate(PICO_PINS):
        left = index < 20
        step = index if left else 39 - index
        pads.append(Pad(
            name, -PICO_ROW if left else PICO_ROW,
            PICO_FIRST_Y + step * PICO_PITCH, PICO_PAD,
            drill=PICO_DRILL, shape="oval" if index in (0,) else "circle",
            note=f"pin {index + 1} {name}"))
    return pads


# --- Model UD / Model BirdD USB-C breakout ---------------------------------
#: Measured off the Model BirdD KiCad files: 36 x 13.5mm, two 1x4 headers
#: 15.24mm apart, M3 holes 28mm apart.
MODELUD_SIZE = (36.0, 13.5)
MODELUD_HEADER_X = 7.62
MODELUD_FIRST_Y = -3.81
#: Dm/Dp rather than D-/D+, and V3V3 rather than 3V3, for the same reason the
#: Pico's pads are named this way: they have to be identifiers in ato.
#: The pads as they are silkscreened on the board: GCD, D- and D+ down one
#: side, GND, 3V, VSYS and 5V down the other.  GCD is the GameCube detect
#: line, which is what makes the USB-C port work with a GameCube cable.
MODELUD_LEFT = ["GCD", "Dm", "Dp"]
MODELUD_RIGHT = ["GND", "V3V", "VSYS", "V5"]
MODELUD_MOUNT_X = 14.0
MODELUD_MOUNT_DRILL = 3.2


def modelud_pads() -> list[Pad]:
    """The mating side of the Model UD's two headers, plus its M3 holes."""
    pads = []
    for side, names in ((-1, MODELUD_LEFT), (1, MODELUD_RIGHT)):
        for index, name in enumerate(names):
            pads.append(Pad(name, side * MODELUD_HEADER_X,
                            MODELUD_FIRST_Y + index * 2.54, 1.7,
                            drill=1.0, shape="rect" if index == 0 else "circle",
                            note=f"Model UD {name}"))
    for side in (-1, 1):
        pads.append(Pad("", side * MODELUD_MOUNT_X, 2.25, MODELUD_MOUNT_DRILL,
                        drill=MODELUD_MOUNT_DRILL, plated=False,
                        note="Model BirdD M3 mounting hole"))
    return pads


def render(name: str, description: str, pads: list[Pad],
           outline: tuple[float, float] = None, back: bool = False) -> str:
    """A footprint file KiCad will open, in the modern s-expression format."""
    lines = [f'(footprint "{name}"',
             f'  (version 20240108)',
             f'  (generator "makoreactor")',
             f'  (layer "{"B.Cu" if back else "F.Cu"}")',
             f'  (descr "{description}")',
             f'  (attr through_hole)',
             f'  (property "Reference" "REF**"',
             # Just clear of the outline, not on top of it: KiCad counts a
             # designator printed over its own silkscreen as an overlap, and
             # it is unreadable on the board either way.
             f'    (at 0 {-(outline[1] / 2 + 1.4) if outline else -2:.4g} 0) (layer "F.SilkS")',
             f'    (effects (font (size 1 1) (thickness 0.15))))',
             f'  (property "Value" "{name}"',
             f'    (at 0 2 0) (layer "F.Fab") (hide yes)',
             f'    (effects (font (size 1 1) (thickness 0.15))))']
    if outline:
        w, h = outline[0] / 2, outline[1] / 2
        for layer, width in (("F.SilkS", 0.12), ("F.CrtYd", 0.05)):
            pad = 0.25 if layer == "F.CrtYd" else 0.0
            corners = [(-w - pad, -h - pad), (w + pad, -h - pad),
                       (w + pad, h + pad), (-w - pad, h + pad)]
            for start, end in zip(corners, corners[1:] + corners[:1]):
                lines.append(f'  (fp_line (start {start[0]:.4g} {start[1]:.4g}) '
                             f'(end {end[0]:.4g} {end[1]:.4g}) '
                             f'(stroke (width {width}) (type solid)) (layer "{layer}"))')
    lines += [pad.render() for pad in pads]
    lines.append(")")
    return "\n".join(lines) + "\n"


def symbol(name: str, pins: list[str]) -> str:
    """A minimal schematic symbol: a box with the pins down one side."""
    body = [f'(kicad_symbol_lib (version 20211014) (generator makoreactor)',
            f'  (symbol "{name}" (in_bom yes) (on_board yes)',
            f'    (property "Reference" "U" (id 0) (at 0 2.54 0)',
            f'      (effects (font (size 1.27 1.27))))',
            f'    (property "Value" "{name}" (id 1) (at 0 -2.54 0)',
            f'      (effects (font (size 1.27 1.27))))',
            f'    (symbol "{name}_0_1"']
    height = max(len(pins) * 2.54 + 2.54, 7.62)
    body.append(f'      (rectangle (start -7.62 {height / 2:.4g}) '
                f'(end 7.62 {-height / 2:.4g})')
    body.append('        (stroke (width 0.254) (type default))'
                ' (fill (type background)))')
    body.append('    )')
    body.append(f'    (symbol "{name}_1_1"')
    for index, pin in enumerate(pins):
        y = height / 2 - 2.54 * (index + 1)
        body.append(f'      (pin passive line (at -12.7 {y:.4g} 0) (length 5.08)')
        body.append(f'        (name "{pin}" (effects (font (size 1.27 1.27))))')
        body.append(f'        (number "{pin}" (effects (font (size 1.27 1.27)))))')
    body += ['    )', '  )', ')']
    return "\n".join(body) + "\n"
