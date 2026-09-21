"""Put every part where the layout says, and draw the board it sits in.

Runs under KiCad's own Python (it needs ``pcbnew``), and reads the numbers
from ``placement.json``, which ``place.py`` writes out of ``makoreactor``.
Two interpreters, one source of truth: KiCad's Python cannot import cadquery,
and the plates are cut from cadquery, so the coordinates travel as JSON.

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/\
Versions/Current/bin/python3 tools/apply_placement.py

``ato build`` writes the netlist and the footprints; this decides where they
go.  Running it again after a rebuild is safe -- it sets absolute positions
and redraws the outline from scratch.
"""

import json
import math
import os
import sys

import pcbnew

MM = pcbnew.FromMM
HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name)) as handle:
        return json.load(handle)


def address_of(footprint):
    """The ``switches[3]``-style address ato stamps into every footprint.

    Matching on this rather than on the designator means a rebuild that
    renumbers SW7 cannot silently move a button to another key.
    """
    if footprint.HasField("atopile_address"):
        return footprint.GetFieldText("atopile_address")
    return None


def to_board(point, board_size):
    """Layout millimetres to board millimetres.

    The plates put the origin at the centre with +Y towards the far edge;
    KiCad puts it at the top left with +Y downwards.
    """
    width, height = board_size
    return pcbnew.VECTOR2I(MM(point[0] + width / 2.0), MM(height / 2.0 - point[1]))


def clear_drawings(board, layer):
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() == layer:
            board.Remove(drawing)


def add_segment(board, start, end, layer, width=0.1):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(start)
    shape.SetEnd(end)
    shape.SetLayer(layer)
    shape.SetWidth(MM(width))
    board.Add(shape)
    return shape


def add_arc(board, centre, start, end, layer, width=0.1):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetLayer(layer)
    shape.SetWidth(MM(width))
    shape.SetArcGeometry(start, mid_point(centre, start, end), end)
    board.Add(shape)
    return shape


def mid_point(centre, start, end):
    """A point on the arc, which is how KiCad wants an arc defined."""
    cx, cy = centre.x, centre.y
    a0 = math.atan2(start.y - cy, start.x - cx)
    a1 = math.atan2(end.y - cy, end.x - cx)
    # Always take the short way round: these are 90 degree corners.
    if a1 - a0 > math.pi:
        a1 -= 2 * math.pi
    if a0 - a1 > math.pi:
        a1 += 2 * math.pi
    radius = math.hypot(start.x - cx, start.y - cy)
    mid = (a0 + a1) / 2.0
    return pcbnew.VECTOR2I(int(cx + radius * math.cos(mid)),
                           int(cy + radius * math.sin(mid)))


def add_circle(board, centre, diameter, layer, width=0.1):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_CIRCLE)
    shape.SetLayer(layer)
    shape.SetWidth(MM(width))
    shape.SetCenter(centre)
    shape.SetEnd(pcbnew.VECTOR2I(centre.x + MM(diameter / 2.0), centre.y))
    board.Add(shape)
    return shape


def draw_outline(board, plan):
    """The board edge and the bolt holes, as the plates are cut.

    A closed shape on Edge.Cuts is the board; a closed shape inside it is a
    hole in the board, which is what the bolts want -- they are the stack's
    own, and nothing is soldered to them.
    """
    width, height = plan["board"]["size"]
    radius = plan["board"]["corner_radius"]
    edge = board.GetLayerID("Edge.Cuts")
    clear_drawings(board, edge)

    left, right = MM(0.0), MM(width)
    top, bottom = MM(0.0), MM(height)
    r = MM(radius)

    def v(x, y):
        return pcbnew.VECTOR2I(int(x), int(y))

    add_segment(board, v(left + r, top), v(right - r, top), edge)
    add_segment(board, v(right, top + r), v(right, bottom - r), edge)
    add_segment(board, v(right - r, bottom), v(left + r, bottom), edge)
    add_segment(board, v(left, bottom - r), v(left, top + r), edge)

    add_arc(board, v(left + r, top + r), v(left + r, top), v(left, top + r), edge)
    add_arc(board, v(right - r, top + r), v(right, top + r), v(right - r, top), edge)
    add_arc(board, v(right - r, bottom - r), v(right - r, bottom), v(right, bottom - r), edge)
    add_arc(board, v(left + r, bottom - r), v(left, bottom - r), v(left + r, bottom), edge)

    for hole in plan["bolts"]:
        add_circle(board, to_board(hole, (width, height)),
                   plan["board"]["bolt_diameter"], edge)


def place(board, plan):
    size = plan["board"]["size"]
    by_address = {}
    for footprint in board.GetFootprints():
        address = address_of(footprint)
        if address:
            by_address[address] = footprint

    placed, missing = 0, []
    for index, point in enumerate(plan["switches"]):
        address = "switches[%d]" % index
        footprint = by_address.get(address)
        if footprint is None:
            missing.append(address)
            continue
        footprint.SetPosition(to_board(point, size))
        footprint.SetOrientationDegrees(0)
        placed += 1

    for part in plan["back"]:
        footprint = by_address.get(part["address"])
        if footprint is None:
            missing.append(part["address"])
            continue
        footprint.SetPosition(to_board(part["at"], size))
        footprint.SetOrientationDegrees(part.get("rotation", 0))
        # The Pico and the USB breakout hang under the board, in the space the
        # wire-space layer already opens up.  Flipping is what puts their pads
        # on the back copper, not just their outline on the back silk.
        if part.get("side") == "back" and footprint.IsFlipped() is False:
            footprint.Flip(footprint.GetPosition(), False)
        placed += 1

    return placed, missing


#: Blocks KiCad 10 writes into ``(setup ...)`` that atopile 0.15.8's PCB
#: parser does not know, and refuses the whole file over.  Stripping them
#: costs nothing -- they are soldermask defaults KiCad puts back on its next
#: save -- and it is what lets the file go round the loop: ato build writes
#: the netlist, this places it, ato build reads it again.
KICAD10_ONLY = ("tenting", "covering", "plugging", "capping", "filling")


def strip_unknown_setup(path):
    """Remove the setup blocks atopile cannot parse, in place."""
    with open(path) as handle:
        text = handle.read()

    removed = []
    for key in KICAD10_ONLY:
        while True:
            start = -1
            for candidate in ("(%s\n" % key, "(%s " % key, "(%s\t" % key):
                found = text.find(candidate)
                if found >= 0 and (start < 0 or found < start):
                    start = found
            if start < 0:
                break
            depth, i = 0, start
            while i < len(text):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            line_start = text.rfind("\n", 0, start) + 1
            tail = i + 1
            while tail < len(text) and text[tail] in "\r\n":
                tail += 1
            text = text[:line_start] + text[tail:]
            removed.append(key)

    if removed:
        with open(path, "w") as handle:
            handle.write(text)
    return removed


def main():
    plan = load("placement.json")
    path = os.path.join(os.path.dirname(HERE), plan["pcb"])
    board = pcbnew.LoadBoard(path)

    placed, missing = place(board, plan)
    draw_outline(board, plan)
    board.Save(path)
    stripped = strip_unknown_setup(path)

    print("placed %d parts" % placed)
    if stripped:
        print("stripped KiCad 10 setup blocks so ato can read it back: %s"
              % ", ".join(sorted(set(stripped))))
    if missing:
        print("MISSING: %s" % ", ".join(missing))
        return 1
    print("wrote %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
