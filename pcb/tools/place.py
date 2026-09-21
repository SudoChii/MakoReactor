"""Place the board from the makoreactor layout.

The switch centres, the outline and the bolt pattern are already defined, in
``makoreactor`` -- the same numbers the plates are cut from.  Re-typing them
into KiCad would mean two sources of truth for the one thing that has to
match, so this reads them and writes them out instead.

    python tools/place.py --format report      # what goes where
    python tools/place.py --format json        # coordinates for apply_placement.py
    python tools/place.py --format dxf         # outline and holes, for the fab

Switch *i* here is ``switches[i]`` in ``mako1.ato``: both follow the order
``layout.layout`` gives, which is why the ato file lists them that way.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import makoreactor as mr  # noqa: E402

#: Side of the switch footprint's courtyard, from tools/footprints.py.  The
#: footprint is a square, so the gap between two of them is how far apart they
#: are along their *worst* axis -- not the straight-line distance between
#: centres, which is what this used to measure and which quietly passed a
#: thumb cluster whose footprints overlapped by a millimetre.
SWITCH_FOOTPRINT = 16.1


#: The mako1 FGC build: the stack in notebooks/mako1_fgc, whose switchplate
#: this board replaces.
def board(width_in: float = 14.0, height_in: float = 6.0,
          layout: str = "square") -> "mr.PlatePart":
    layouts = {
        "square": mr.SquareCapLeverless,
        "circle": mr.CircleCapLeverless,
        "gccmx": mr.Gccmx,
        "hadoe": mr.Mako1Hadoe,
    }
    return mr.Switchplate(
        width=mr.in2mm(width_in),
        height=mr.in2mm(height_in),
        layout=layouts[layout](),
    )


def positions(part) -> list[tuple[float, float]]:
    """Switch centres, in the order ``mako1.ato`` declares them."""
    return [tuple(point) for point in part.layout]


def report(part) -> str:
    points = positions(part)
    lines = [
        f"board      {part.width:.2f} x {part.height:.2f} mm, "
        f"corner radius {part.fillet_radius:.1f}",
        f"switches   {len(points)}",
        f"bolts      {len(part.mounting_points())} x "
        f"{part.hole_diameter:.1f}mm, the stack's own pattern",
        "",
        "  i  designator      x        y     group",
    ]
    groups = []
    for name in mr.GROUPS:
        groups += [name] * len(part.layout.placed(name))
    for index, ((x, y), group) in enumerate(zip(points, groups)):
        lines.append(f"{index:3d}  SW{index + 1:<2d}       {x:8.2f} {y:8.2f}   {group}")
    lines.append("")
    for x, y in part.mounting_points():
        lines.append(f"     bolt        {x:8.2f} {y:8.2f}")
    lines.append("")
    lines += fits(part)
    return "\n".join(lines)


#: Where the two boards that hang underneath go, in layout millimetres.
#:
#: The Model UD sits on the centreline against the back edge, because that is
#: where ``WireSpaceModelU`` already cuts the USB-C pocket -- x=0, and the
#: pocket runs from 6.25mm to 15.25mm in from the edge.  The Pico goes on its
#: side in the middle of the board rather than off in a corner: it is the far
#: end of twenty traces, and a corner would make every one of them cross the
#: whole board.  Both are checked against the layout by :func:`fits`.
BACK_PARTS = [
    {"address": "usb.package", "at": (0.0, 57.0), "rotation": 0,
     "size": (36.0, 13.5), "side": "back", "what": "Model UD, at the USB pocket"},
    {"address": "pico.package", "at": (-6.0, -24.0), "rotation": 90,
     "size": (21.0, 51.0), "side": "back", "what": "Pi Pico, middle of the board"},
]


#: What hangs under the board, in millimetres below its underside.  These are
#: the numbers that decide whether the stack still closes, so they are written
#: down rather than guessed at in a comment.
BELOW_BOARD = [
    ("MX switch pins", 3.3, "solder side of a 5-pin MX"),
    ("Choc hotswap socket", 1.85, "Kailh CPG135001S30, the deepest thing on a Choc build"),
    ("Pi Pico, soldered flat", 2.4, "its own board plus what is on the bottom of it"),
    ("Pi Pico, on 2.54mm headers", 11.0, "socket and header body, the tall option"),
    ("Model UD", 5.0, "its own board plus the USB-C shell"),
]


def stack(part) -> str:
    """Whether this board still fits the stack it is going into.

    The PCB replaces a 3.175mm plate with a 1.6mm one, which is not a detail:
    1.6mm is what a switch clips into, and 3.175mm is what the bolts were cut
    for.  Something has to give, and this says how much.
    """
    import makoreactor as mr

    space = mr.WireSpaceModelU(width=part.width, height=part.height, n_modelu=2,
                               layout=part.layout)
    pcb = 1.6
    lines = [
        "the board against the stack it replaces",
        "",
        f"  switchplate       {part.depth:.3f}mm  <- the PCB is {pcb:.2f}mm",
        f"  difference        {part.depth - pcb:+.3f}mm to make up",
        f"  wire space below  {space.part_depth():.2f}mm (n_modelu=2)",
        "",
        "  1.6mm is not a compromise, it is the right number: an MX or Choc",
        "  switch clips into a 1.5mm plate, which is what a PCB of this",
        "  thickness gives it.  The plate it replaces was 1/8in because it was",
        "  acrylic and had to be stiff.  So shim the difference rather than",
        "  thicken the board -- or set Switchplate(depth=1.6) and let the",
        f"  stack come out {part.depth - pcb:.3f}mm shorter.",
        "",
        "  under the board:",
    ]
    room = space.part_depth()
    for what, depth, note in BELOW_BOARD:
        fits = "fits" if depth < room else "DOES NOT FIT"
        lines.append(f"    {what:<28} {depth:5.2f}mm   {fits}, {room - depth:+.2f}mm spare   ({note})")

    tallest = max(depth for what, depth, _ in BELOW_BOARD if "headers" not in what)
    lines += [
        "",
        f"  worst case soldered flat is {tallest:.2f}mm into {room:.2f}mm, so the",
        "  stack closes; on headers the Pico is the tall part and wants the",
        "  full 12.7mm, which is why n_modelu=2 rather than 1.",
    ]
    return "\n".join(lines)


def placement(part) -> str:
    """The coordinates, as JSON for ``apply_placement.py``.

    KiCad's Python cannot import cadquery, so the numbers travel as a file
    rather than as an import -- but they are still generated from the part the
    plates are cut from, not typed twice.
    """
    import json

    return json.dumps({
        "pcb": "layout/default/default.kicad_pcb",
        "board": {
            "size": [part.width, part.height],
            "corner_radius": part.fillet_radius,
            "bolt_diameter": part.hole_diameter,
        },
        "switches": [[round(x, 4), round(y, 4)] for x, y in positions(part)],
        "bolts": [[round(x, 4), round(y, 4)] for x, y in part.mounting_points()],
        "back": [
            {"address": item["address"], "at": list(item["at"]),
             "rotation": item["rotation"], "side": item["side"], "what": item["what"]}
            for item in BACK_PARTS
        ],
    }, indent=2)


def kicad_script(part) -> str:
    """A script for KiCad's scripting console: places what ato has already
    netlisted, so the board matches the plates without hand-placing 20 parts.

    KiCad's Y axis points down and the plates' does not, so Y is negated here.
    """
    points = positions(part)
    lines = [
        '"""Run in KiCad: Tools > Scripting Console. Places the switches, the',
        'bolt holes and the outline from makoreactor\'s layout."""',
        "import pcbnew",
        "",
        "MM = pcbnew.FromMM",
        "board = pcbnew.GetBoard()",
        "",
        "SWITCHES = [",
    ]
    lines += [f"    ({x:.4f}, {y:.4f})," for x, y in points]
    lines += [
        "]",
        "BOLTS = [",
    ]
    lines += [f"    ({x:.4f}, {y:.4f})," for x, y in part.mounting_points()]
    lines += [
        "]",
        f"BOLT_DIAMETER = {part.hole_diameter}",
        f"BOARD = ({part.width}, {part.height}, {part.fillet_radius})",
        "",
        "origin = pcbnew.VECTOR2I(MM(BOARD[0] / 2), MM(BOARD[1] / 2))",
        "",
        "",
        "def find(index):",
        "    \"\"\"Match on the address ato stamps into each footprint, so a",
        "    reshuffled designator cannot silently move a button.\"\"\"",
        "    address = 'switches[%d]' % index",
        "    for footprint in board.GetFootprints():",
        "        try:",
        "            if footprint.GetProperty('atopile_address') == address:",
        "                return footprint",
        "        except Exception:",
        "            pass",
        "    return board.FindFootprintByReference('SW%d' % (index + 1))",
        "",
        "placed = 0",
        "for index, (x, y) in enumerate(SWITCHES):",
        "    footprint = find(index)",
        "    if footprint is None:",
        "        print('no footprint for switches[%d]' % index)",
        "        continue",
        "    footprint.SetPosition(pcbnew.VECTOR2I(MM(x), MM(-y)) + origin)",
        "    placed += 1",
        "",
        "# Bolt holes and the outline come in with the DXF this tool also",
        "# writes -- File > Import > Graphics, onto Edge.Cuts.",
        "",
        "pcbnew.Refresh()",
        "print('placed %d of %d switches' % (placed, len(SWITCHES)))",
    ]
    return "\n".join(lines) + "\n"


def dxf(part, out: pathlib.Path = pathlib.Path("board_outline.dxf")) -> str:
    """Outline and bolt holes as DXF, from the same part the plates are cut
    from -- this is the board shape, for KiCad's Edge.Cuts or for the fab."""
    from cadquery import exporters

    plate = part._cut_mounting_holes(part.blank())
    exporters.export(plate.edges(">Z"), str(out))
    return f"wrote {out} ({out.stat().st_size} bytes)"


def fits(part) -> list[str]:
    """Whether the switches actually clear each other and the bolts.

    The footprint is 19.05mm square and the layout was drawn for 20.5mm caps,
    so this should never be tight -- but the layout is a parameter, and a
    tighter one would put copper through copper.
    """
    import math

    points = positions(part)
    half = SWITCH_FOOTPRINT / 2
    notes = []

    def box_gap(a, b, size=SWITCH_FOOTPRINT):
        """How far apart two axis-aligned squares are -- negative if they
        overlap."""
        return max(abs(a[0] - b[0]), abs(a[1] - b[1])) - size

    gap = min(box_gap(a, b) for i, a in enumerate(points) for b in points[i + 1:])
    notes.append(f"closest two switch footprints: {gap:+.2f}mm")

    # The caps have to clear each other too, and they are wider than the
    # switch.  Choc caps are 17.5mm; MX caps are 18mm and this layout puts
    # some buttons 18.5mm apart, so MX is the tighter of the two.
    for cap, what in ((17.5, "Choc keycaps"), (18.0, "MX keycaps")):
        caps = min(box_gap(a, b, cap)
                   for i, a in enumerate(points) for b in points[i + 1:])
        notes.append(f"closest two {what}: {caps:+.2f}mm")

    bolt = min(
        math.dist(point, hole) - half - part.hole_diameter / 2
        for point in points for hole in part.mounting_points()
    )
    notes.append(f"closest switch to a bolt hole: {bolt:+.2f}mm")

    edge = min(
        min(part.width / 2 - abs(x), part.height / 2 - abs(y)) - half
        for x, y in points
    )
    notes.append(f"closest switch to the board edge: {edge:+.2f}mm")

    # The two boards underneath have to miss the switch bodies and the bolts
    # as well -- they are on the other side, but the through-holes are not.
    for item in BACK_PARTS:
        cx, cy = item["at"]
        w, h = item["size"]
        if item["rotation"] % 180:
            w, h = h, w
        near_switch = min(
            math.hypot(max(abs(x - cx) - w / 2, 0), max(abs(y - cy) - h / 2, 0)) - half
            for x, y in points
        )
        near_bolt = min(
            math.hypot(max(abs(x - cx) - w / 2, 0), max(abs(y - cy) - h / 2, 0))
            - part.hole_diameter / 2
            for x, y in part.mounting_points()
        )
        inside = min(part.width / 2 - abs(cx) - w / 2, part.height / 2 - abs(cy) - h / 2)
        notes.append(f"{item['what']}: {near_switch:+.2f}mm to a switch, "
                     f"{near_bolt:+.2f}mm to a bolt, {inside:+.2f}mm inside the edge")
        gap = min(gap, near_switch, near_bolt, inside)

    if min(gap, bolt, edge) < 0:
        notes.append("FAIL: something overlaps -- the layout will not fit this board")
    return notes


def wiring(part) -> list[str]:
    """Check mako1.ato against the layout: one switch per button, one GPIO
    each, and no GPIO used twice.

    The mapping is written out by hand in the ato file -- it has to be, since
    it is a choice about which button does what -- so this is the check that
    the hand-written part still lines up with the generated part.
    """
    import re

    source = (pathlib.Path(__file__).parent.parent / "mako1.ato").read_text()
    used = re.findall(r"switches\[(\d+)\]\.A ~ pico\.gpio\[(\d+)\]", source)
    switches = {int(sw) for sw, _ in used}
    gpios = [int(gp) for _, gp in used]

    notes = [f"mako1.ato wires {len(used)} switches to {len(set(gpios))} GPIOs"]
    expected = len(positions(part))
    if switches != set(range(expected)):
        missing = sorted(set(range(expected)) - switches)
        notes.append(f"FAIL: layout has {expected} buttons; "
                     f"switches {missing} are not wired")
    if len(gpios) != len(set(gpios)):
        doubled = sorted({gp for gp in gpios if gpios.count(gp) > 1})
        notes.append(f"FAIL: GP{doubled} wired to more than one switch")
    for gp in gpios:
        if gp in (23, 24, 25) or gp > 28:
            notes.append(f"FAIL: GP{gp} is not on the Pico's header")

    # The mapping is not free: it is HayBox's own config/pico, so a board built
    # to this pinout runs stock firmware with no config edit.  GP28 is not a
    # button -- HayBox uses it as joybus_data, which is the GameCube detect
    # line from the Model UD.
    haybox = {2, 3, 4, 5, 26, 21, 19, 17, 27, 22, 20, 18, 6, 7, 14, 15, 13, 12, 16, 0}
    if set(gpios) != haybox:
        extra = sorted(set(gpios) - haybox)
        missing = sorted(haybox - set(gpios))
        notes.append(f"FAIL: pinout has drifted from HayBox config/pico "
                     f"(extra {extra}, missing {missing})")
    if 28 in gpios:
        notes.append("FAIL: GP28 is HayBox's joybus_data, not a button")
    if not any(note.startswith("FAIL") for note in notes):
        notes.append("ok: every button has a GPIO and no GPIO is shared")
    return notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", default="report",
                        choices=["report", "json", "stack", "kicad", "dxf", "check"])
    parser.add_argument("--width", type=float, default=14.0, help="inches")
    parser.add_argument("--height", type=float, default=6.0, help="inches")
    parser.add_argument("--layout", default="square",
                        choices=["square", "circle", "gccmx", "hadoe"])
    args = parser.parse_args(argv)

    part = board(args.width, args.height, args.layout)
    if args.format == "check":
        notes = fits(part) + wiring(part)
        print("\n".join(notes))
        return 1 if any(note.startswith("FAIL") for note in notes) else 0

    print({"report": report, "json": placement, "stack": stack,
           "kicad": kicad_script, "dxf": dxf}[args.format](part))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
