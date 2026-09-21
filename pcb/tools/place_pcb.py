"""Place the board from the layout, by editing the PCB file directly.

This does what KiCad's own Python would do -- move every footprint onto its
layout centre, flip the two boards that hang underneath, draw the outline and
the bolt holes -- but without going through ``pcbnew``, and that is deliberate.

KiCad 10 rewrites a board it saves: it drops the net table and writes pad nets
by name only (``(net "gnd")`` rather than ``(net 12 "gnd")``).  atopile 0.15.8
cannot read that back, so a single save from pcbnew ends the round trip -- the
next ``ato build`` fails on its own layout file.  Editing the text in place
keeps the file in the dialect both tools read, so the loop stays open:

    ato build            # netlist and footprints
    place_pcb.py         # where everything goes
    ato build            # still reads its own file

Coordinates come from ``placement.json``, which ``place.py`` writes out of
``makoreactor`` -- the same numbers the plates are cut from.

    python tools/place_pcb.py [--pcb path] [--plan tools/placement.json]
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re

#: Layers that swap when a footprint moves to the other side of the board.
FLIPPED = {
    "F.Cu": "B.Cu", "B.Cu": "F.Cu",
    "F.SilkS": "B.SilkS", "B.SilkS": "F.SilkS",
    "F.Mask": "B.Mask", "B.Mask": "F.Mask",
    "F.Paste": "B.Paste", "B.Paste": "F.Paste",
    "F.CrtYd": "B.CrtYd", "B.CrtYd": "F.CrtYd",
    "F.Fab": "B.Fab", "B.Fab": "F.Fab",
}


def block_at(text: str, start: int) -> tuple[int, int]:
    """The span of the s-expression beginning at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise ValueError("unbalanced s-expression")


def blocks(text: str, tag: str):
    """Spans of every ``(tag ...)`` in ``text``, outermost first."""
    for match in re.finditer(r"\(%s[\s\n]" % re.escape(tag), text):
        yield block_at(text, match.start())


def footprint_spans(text: str) -> dict[str, tuple[int, int]]:
    """Footprint spans keyed by the address ato stamps into each one.

    Addresses rather than designators: a rebuild is free to renumber SW7, and
    a silently moved button is the one mistake this whole file exists to
    avoid.
    """
    found = {}
    for start, end in blocks(text, "footprint"):
        source = text[start:end]
        address = re.search(r'\(property "atopile_address" "([^"]+)"', source)
        if address:
            found[address.group(1)] = (start, end)
    return found


def to_board(point, size) -> tuple[float, float]:
    """Layout millimetres to board millimetres.

    The plates put the origin at the middle of the board with +Y towards the
    far edge; KiCad puts it at the top left corner with +Y downwards.
    """
    width, height = size
    return point[0] + width / 2.0, height / 2.0 - point[1]


def mm(value: float) -> str:
    text = ("%.4f" % value).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def move(source: str, position, rotation: float) -> str:
    """Set a footprint's position and angle."""
    x, y = position
    at = re.search(r"\(at [-\d.]+ [-\d.]+(?: [-\d.]+)?\)", source)
    placed = "(at %s %s%s)" % (mm(x), mm(y), " %s" % mm(rotation) if rotation else "")
    return source[:at.start()] + placed + source[at.end():]


def flip(source: str) -> str:
    """Move a footprint to the back of the board.

    Mirrors it about its own Y axis and swaps every front layer for its back
    counterpart, which is what KiCad does when you press F -- the pads have to
    end up on back copper, not just the outline on back silk.
    """
    def mirror_x(match):
        return "(at %s %s%s)" % (mm(-float(match.group(1))), match.group(2),
                                 match.group(3) or "")

    def mirror_point(match):
        return "(%s %s %s)" % (match.group(1), mm(-float(match.group(2))), match.group(3))

    body = source
    # Everything inside a footprint is relative to it, so mirroring is just a
    # sign flip on x -- except the footprint's own (at ...), which is where it
    # sits on the board and is set by move().
    head, rest = body.split("\n", 1)
    rest = re.sub(r"\(at ([-\d.]+) ([-\d.]+)( [-\d.]+)?\)", mirror_x, rest)
    rest = re.sub(r"\((start|end|center|mid) ([-\d.]+) ([-\d.]+)\)", mirror_point, rest)
    rest = re.sub(r'"(F|B)\.(Cu|SilkS|Mask|Paste|CrtYd|Fab)"',
                  lambda m: '"%s"' % FLIPPED["%s.%s" % (m.group(1), m.group(2))], rest)
    return head + "\n" + clear_reference(mirror_text(rest))


def clear_reference(source: str) -> str:
    """Put the designator outside the footprint's own outline.

    ato positions reference fields itself, and on the two big boards that lands
    it on top of their silkscreen -- which KiCad counts as an overlap, and
    which is unreadable in any case.  The outline is right there in the
    footprint, so put the text just above it.
    """
    ys = [float(m.group(2)) for m in
          re.finditer(r"\((?:start|end) ([-\d.]+) ([-\d.]+)\)", source)]
    if not ys:
        return source
    # 2.5mm, not 1.4: KiCad measures the text's whole box, which is
    # taller than the 1mm glyphs, and counts the margin as an overlap.
    top = min(ys) - 2.5

    found = source.find('(property "Reference"')
    if found < 0:
        return source
    start, end = block_at(source, found)
    block = source[start:end]
    block = re.sub(r"\(at [-\d.]+ [-\d.]+( [-\d.]+)?\)",
                   lambda m: "(at 0 %s%s)" % (mm(top), m.group(1) or ""), block, count=1)
    return source[:start] + block + source[end:]


def mirror_text(source: str) -> str:
    """Mirror any text that came along to the back.

    Text on back copper reads backwards unless it is mirrored; KiCad's DRC
    calls unmirrored text on a back layer a violation, and it is right --
    a designator you cannot read is not doing its job.
    """
    out, index = [], 0
    while True:
        found = source.find("(effects", index)
        if found < 0:
            out.append(source[index:])
            return "".join(out)
        start, end = block_at(source, found)
        block = source[start:end]
        if "(justify" in block:
            # Keep whatever alignment it already had and add the mirror to it:
            # a reference that is right-aligned still needs to read the right
            # way round on the back.
            if "mirror" not in block:
                block = re.sub(r"\(justify ([^)]*)\)", r"(justify \1 mirror)", block, count=1)
        else:
            indent = re.match(r"[\t ]*", source[source.rfind("\n", 0, start) + 1:]).group(0)
            block = block[:-1].rstrip() + "\n%s\t(justify mirror)\n%s)" % (indent, indent)
        out.append(source[index:start])
        out.append(block)
        index = end


def outline(plan) -> str:
    """The board edge and the bolt holes, in the file's own dialect.

    A closed shape on Edge.Cuts is the board outline; closed shapes inside it
    are holes in the board, which is what the bolts are -- they are the
    stack's own pattern and nothing is soldered to them.
    """
    width, height = plan["board"]["size"]
    radius = float(plan["board"]["corner_radius"])
    lines = []

    def line(x0, y0, x1, y1):
        lines.append(
            '\t(gr_line\n\t\t(start %s %s)\n\t\t(end %s %s)\n'
            '\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type default)\n\t\t)\n'
            '\t\t(layer "Edge.Cuts")\n\t)' % (mm(x0), mm(y0), mm(x1), mm(y1))
        )

    def arc(cx, cy, start_angle):
        """A 90 degree corner, given as start, a point on it, and end."""
        points = []
        for step in (0.0, 0.5, 1.0):
            angle = math.radians(start_angle + 90.0 * step)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        (sx, sy), (mx, my), (ex, ey) = points
        lines.append(
            '\t(gr_arc\n\t\t(start %s %s)\n\t\t(mid %s %s)\n\t\t(end %s %s)\n'
            '\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type default)\n\t\t)\n'
            '\t\t(layer "Edge.Cuts")\n\t)'
            % (mm(sx), mm(sy), mm(mx), mm(my), mm(ex), mm(ey))
        )

    left, right, top, bottom = 0.0, width, 0.0, height
    line(left + radius, top, right - radius, top)
    line(right, top + radius, right, bottom - radius)
    line(right - radius, bottom, left + radius, bottom)
    line(left, bottom - radius, left, top + radius)

    # KiCad arcs run counter-clockwise on screen, and screen Y points down.
    arc(right - radius, top + radius, -90)
    arc(right - radius, bottom - radius, 0)
    arc(left + radius, bottom - radius, 90)
    arc(left + radius, top + radius, 180)

    for hole in plan["bolts"]:
        x, y = to_board(hole, (width, height))
        lines.append(
            '\t(gr_circle\n\t\t(center %s %s)\n\t\t(end %s %s)\n'
            '\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type default)\n\t\t)\n'
            '\t\t(fill no)\n\t\t(layer "Edge.Cuts")\n\t)'
            % (mm(x), mm(y), mm(x + plan["board"]["bolt_diameter"] / 2.0), mm(y))
        )
    return "\n".join(lines) + "\n"


def ground_pour(plan, net_number: int, net_name: str) -> str:
    """A ground zone over the whole board, on both sides.

    Twenty of the twenty-three nets on this board are a switch to a GPIO; the
    twenty-first is ground, and every switch has a pole on it.  Routing that
    as traces would be twenty wires converging on one pin.  A pour is what
    every keyboard does instead: the copper is already there, and each pad
    connects to it where it sits.
    """
    width, height = plan["board"]["size"]
    inset = plan["board"].get("pour_inset", 0.5)
    points = [(inset, inset), (width - inset, inset),
              (width - inset, height - inset), (inset, height - inset)]
    corners = "\n".join("\t\t\t\t(xy %s %s)" % (mm(x), mm(y)) for x, y in points)

    zones = []
    for layer in ("F.Cu", "B.Cu"):
        zones.append(
            '\t(zone\n'
            '\t\t(net %d)\n\t\t(net_name "%s")\n\t\t(layer "%s")\n'
            '\t\t(name "%s")\n\t\t(hatch edge 0.5)\n'
            # Solid, not thermal relief: a 3mm switch pad with a 0.5mm
            # spoke is a starved thermal, and this is a ground plane whose
            # whole job is to be low impedance.  Hand soldering a pad on a
            # pour is the trade, and it is the usual one on a keyboard.
            '\t\t(connect_pads yes\n\t\t\t(clearance 0.5)\n\t\t)\n'
            '\t\t(min_thickness 0.25)\n\t\t(filled_areas_thickness no)\n'
            '\t\t(fill\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t)\n'
            '\t\t(polygon\n\t\t\t(pts\n%s\n\t\t\t)\n\t\t)\n\t)'
            % (net_number, net_name, layer, net_name, corners)
        )
    return "\n".join(zones) + "\n"


def net_number(text: str, name: str) -> int | None:
    """The number the file gave a net -- zones refer to it by number."""
    found = re.search(r'\(net (\d+) "%s"\)' % re.escape(name), text)
    return int(found.group(1)) if found else None


def strip_zones(text: str) -> str:
    """Drop any pour already there, so this can be re-run."""
    while True:
        for start, end in blocks(text, "zone"):
            line_start = text.rfind("\n", 0, start) + 1
            tail = end
            while tail < len(text) and text[tail] in "\r\n":
                tail += 1
            text = text[:line_start] + text[tail:]
            break
        else:
            return text


def strip_outline(text: str) -> str:
    """Drop any Edge.Cuts graphics already there, so this can be re-run."""
    for tag in ("gr_line", "gr_arc", "gr_circle", "gr_rect", "gr_poly"):
        while True:
            for start, end in blocks(text, tag):
                if '(layer "Edge.Cuts")' in text[start:end]:
                    line_start = text.rfind("\n", 0, start) + 1
                    tail = end
                    while tail < len(text) and text[tail] in "\r\n":
                        tail += 1
                    text = text[:line_start] + text[tail:]
                    break
            else:
                break
    return text


def place(text: str, plan) -> tuple[str, list[str]]:
    size = plan["board"]["size"]
    wanted = [("switches[%d]" % i, point, 0.0, False)
              for i, point in enumerate(plan["switches"])]
    wanted += [(part["address"], part["at"], float(part.get("rotation", 0)),
                part.get("side") == "back") for part in plan["back"]]

    missing = []
    # Back to front, so that editing one footprint does not shift the spans of
    # the ones before it.
    spans = footprint_spans(text)
    for address, point, rotation, back in sorted(
        wanted, key=lambda item: spans.get(item[0], (0, 0))[0], reverse=True
    ):
        if address not in spans:
            missing.append(address)
            continue
        start, end = spans[address]
        source = text[start:end]
        if back and '(layer "F.Cu")' in source.split("\n", 2)[1]:
            source = flip(source)
        source = move(source, to_board(point, size), rotation)
        text = text[:start] + source + text[end:]

    return text, missing


def main(argv=None) -> int:
    here = pathlib.Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=pathlib.Path, default=here / "placement.json")
    parser.add_argument("--pcb", type=pathlib.Path, default=None)
    parser.add_argument("--strip-zones", action="store_true",
                        help="only remove the copper pours, and stop")
    args = parser.parse_args(argv)

    plan = json.loads(args.plan.read_text())
    pcb = args.pcb or here.parent / plan["pcb"]
    text = pcb.read_text()

    if args.strip_zones:
        # atopile 0.15.8 segfaults reading a board with a zone on it -- code
        # -11, no message.  So the pour comes off before a build and goes back
        # on after, which is what tools/build.sh does.  Nothing is lost: the
        # pour is generated, not drawn by hand.
        stripped = strip_zones(text)
        pcb.write_text(stripped)
        print("removed the pours so ato can read the board")
        return 0

    text, missing = place(text, plan)
    text = strip_zones(strip_outline(text))

    ground = plan["board"].get("ground_net", "gnd")
    number = net_number(text, ground)
    addition = outline(plan)
    if number is not None:
        addition += ground_pour(plan, number, ground)

    closing = text.rstrip().rfind("\n)")
    text = text[:closing + 1] + addition + ")\n"
    pcb.write_text(text)

    print("placed %d switches and %d boards underneath"
          % (len(plan["switches"]), len(plan["back"])))
    print("drew the outline, %s corners, and %d bolt holes"
          % (plan["board"]["corner_radius"], len(plan["bolts"])))
    if number is None:
        print("no '%s' net found, so no ground pour" % ground)
    else:
        print("poured '%s' on both sides" % ground)
    if missing:
        print("MISSING: %s" % ", ".join(missing))
        return 1
    print("wrote %s" % pcb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
