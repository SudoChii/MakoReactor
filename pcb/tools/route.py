"""Route the signal nets, so the board has copper on it and not just a netlist.

Ground is a pour -- every switch has a pole on it and twenty traces converging
on one pin would be silly -- but the twenty button signals and the three power
and data links have to be actual traces, and atopile does not route.  Nor does
`kicad-cli`: there is no autorouter and no Specctra export to hand off to one.
So this is a small maze router.

It is deliberately simple: one layer, a grid, and A* per net in order of
length, with no rip-up.  That is enough here because the board is mostly empty
-- twenty switches on a 355 x 152mm plate with the Pico in the middle -- and
because anything it cannot route it says so about rather than bodging.  Check
its work with `kicad-cli pcb drc`; that is what it was developed against.

    python tools/route.py            # route, and report what it did
    python tools/route.py --clear    # take the traces back off
"""

from __future__ import annotations

import argparse
import heapq
import math
import pathlib
import re

#: Track geometry, in millimetres.  0.3mm at 0.2mm clearance is comfortable
#: for a 2-layer board.
TRACK_WIDTH = 0.2
CLEARANCE = 0.2  # the board rule; planning tighter just moves the failure to DRC
#: 0.2mm, and only orthogonal steps on it.  0.5mm could not thread the gap
#: between two of the Pico's pads -- they are 2.54mm apart with 1.7mm pads,
#: which leaves 0.84mm, enough for one track but only if the grid has a line
#: in it.  Diagonals looked tidier and were
#: wrong twice over: two diagonals can cross without sharing a cell, so the
#: grid cannot see the crossing, and parallel diagonals sit 0.354mm apart when
#: they need 0.5mm.  KiCad found both.
GRID = 0.2
#: What one track has to keep clear of another: both half-widths and the gap.
TRACK_KEEPOUT = TRACK_WIDTH + CLEARANCE
#: Two layers, and the front is not one of them.  Signals go on the back,
#: where the Pico and the breakout already are; the front is left to the
#: ground plane, unbroken.  That is the whole point of a ground plane -- a
#: signal crossing it cuts the return path underneath every track that shares
#: it -- so the router is given one side and has to fit.
LAYERS = ("B.Cu",)
EDGE_KEEPOUT = 1.0

#: Kept for the day the board needs a second signal layer; with one layer in
#: :data:`LAYERS` the router never offers a via move.
VIA_DIAMETER = 0.6
VIA_DRILL = 0.3
VIA_COST = 4.0
#: The board asks for 0.25mm around a hole, which is more than it asks for
#: around copper.  Planning to the copper number put tracks 0.075mm from
#: drills, so holes get their own, larger, number.
HOLE_CLEARANCE = 0.3


def blocks(text: str, tag: str):
    for match in re.finditer(r"\(%s[\s\n]" % re.escape(tag), text):
        depth, i = 0, match.start()
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    yield match.start(), i + 1
                    break
            i += 1


class Pad:
    """A pad, where it really is on the board."""

    def __init__(self, x, y, radius, drill, net_number, net_name, reference):
        self.x, self.y = x, y
        self.radius = radius
        self.drill = drill
        self.net_number = net_number
        self.net_name = net_name
        self.reference = reference

    def __repr__(self):
        return "%s@(%.1f,%.1f) %s" % (self.reference, self.x, self.y, self.net_name)


def read_pads(text: str) -> list[Pad]:
    """Every pad on the board, rotated and translated into board coordinates."""
    pads = []
    for start, end in blocks(text, "footprint"):
        source = text[start:end]
        head = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", source)
        fx, fy = float(head.group(1)), float(head.group(2))
        angle = math.radians(float(head.group(3) or 0))
        reference = re.search(r'\(property "Reference" "([^"]+)"', source)
        reference = reference.group(1) if reference else "?"

        for pad_start, pad_end in blocks(source, "pad"):
            pad = source[pad_start:pad_end]
            at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pad)
            size = re.search(r"\(size ([\d.]+) ([\d.]+)\)", pad)
            net = re.search(r'\(net (\d+) "([^"]*)"\)', pad)
            if not at or not size:
                continue
            px, py = float(at.group(1)), float(at.group(2))
            # A footprint's own angle turns its pads about its origin.  KiCad
            # measures that angle anticlockwise while Y runs down the page,
            # which is why the sine terms come out this way round.
            rx = px * math.cos(angle) + py * math.sin(angle)
            ry = -px * math.sin(angle) + py * math.cos(angle)
            drill = re.search(r"\(drill ([\d.]+)", pad)
            # Copper and hole are kept apart on purpose.  They have different
            # clearance rules, and folding the hole's larger number into the
            # whole pad closed the 0.84mm gap between two of the Pico's pads
            # -- which is the only way out for the inner row.
            radius = max(float(size.group(1)), float(size.group(2))) / 2
            hole = (float(drill.group(1)) / 2) if drill else 0.0
            pads.append(Pad(fx + rx, fy + ry, radius, hole,
                            int(net.group(1)) if net else None,
                            net.group(2) if net else None, reference))
    return pads


class Grid:
    """Somewhere to route in, with the pads and the board edge marked off."""

    def __init__(self, board, pads, holes):
        width, height = board["size"]
        self.nx = int(width / GRID) + 1
        self.ny = int(height / GRID) + 1
        self.pads = pads
        # blocked[i] is the net that owns a cell, or None if nobody does.
        self.blocked = [[None] * (self.nx * self.ny) for _ in LAYERS]

        radius = float(board["corner_radius"])
        keep = EDGE_KEEPOUT + TRACK_WIDTH / 2
        for index in range(self.nx * self.ny):
            x, y = self.point(index)
            if not inside_rounded_rect(x, y, width, height, radius, keep):
                for layer in range(len(LAYERS)):
                    self.blocked[layer][index] = "edge"

        for pad in pads:
            # A pad on no net is still copper, and a hole is still a hole.
            # Left as None these read as free space, and the tracks went
            # straight over the MX pins and the switch mounting holes.
            owner = pad.net_number if pad.net_number else "pad"
            keepout = max(pad.radius + CLEARANCE,
                          pad.drill + HOLE_CLEARANCE) + TRACK_WIDTH / 2
            self.stamp(pad.x, pad.y, keepout, owner)
        # The bolt holes are cut out of the board, so they are edge too.
        for x, y, hole in holes:
            self.stamp(x, y, hole + EDGE_KEEPOUT + TRACK_WIDTH / 2, "edge")

    def index(self, ix, iy):
        return iy * self.nx + ix

    def point(self, index):
        # Rounded: these coordinates are compared to decide whether a path is
        # still going the same way, and 4.2 - 4.0 is not 4.4 - 4.2 in binary.
        # Unrounded, every single step read as a corner, which turned 17 paths
        # into eleven thousand segments with gaps between them.
        return (round((index % self.nx) * GRID, 4),
                round((index // self.nx) * GRID, 4))

    def cell(self, x, y):
        return int(round(x / GRID)), int(round(y / GRID))

    def stamp(self, x, y, radius, owner, layer=None):
        """Mark a disc as belonging to ``owner`` -- its own net may pass.

        ``layer`` of None means both sides, which is what a through-hole pad
        and a via both are.
        """
        layers = range(len(LAYERS)) if layer is None else (layer,)
        cx, cy = self.cell(x, y)
        reach = int(radius / GRID) + 1
        for iy in range(max(cy - reach, 0), min(cy + reach + 1, self.ny)):
            for ix in range(max(cx - reach, 0), min(cx + reach + 1, self.nx)):
                px, py = ix * GRID, iy * GRID
                if math.hypot(px - x, py - y) <= radius:
                    index = self.index(ix, iy)
                    for which in layers:
                        if self.blocked[which][index] is None:
                            self.blocked[which][index] = owner
                        elif self.blocked[which][index] != owner:
                            self.blocked[which][index] = "shared"

    def free(self, index, layer, net):
        """Can this net use this cell, on this side?"""
        held = self.blocked[layer][index]
        return held is None or held == net

    def via_fits(self, index, net):
        """Is there room for a whole via here, on both sides?

        A via is much fatter than the track that leads to it, so checking the
        one cell it starts from is not enough -- that is how vias ended up
        0.075mm from someone else's track.
        """
        radius = VIA_DIAMETER / 2 + HOLE_CLEARANCE + TRACK_WIDTH / 2
        cx, cy = index % self.nx, index // self.nx
        reach = int(radius / GRID) + 1
        for iy in range(max(cy - reach, 0), min(cy + reach + 1, self.ny)):
            for ix in range(max(cx - reach, 0), min(cx + reach + 1, self.nx)):
                if math.hypot((ix - cx) * GRID, (iy - cy) * GRID) > radius:
                    continue
                spot = self.index(ix, iy)
                for layer in range(len(LAYERS)):
                    if not self.free(spot, layer, net):
                        return False
        return True

    def route(self, start, goal, net):  # noqa: C901
        """A* from one pad to the other, over both sides of the board.

        A node is a cell *and* a layer; changing layer is a move like any
        other, priced at :data:`VIA_COST` so the router only takes one when
        going round is worse than going through.
        """
        sx, sy = self.cell(*start)
        gx, gy = self.cell(*goal)
        starts = [(self.index(sx, sy), layer) for layer in range(len(LAYERS))]
        goals = {(self.index(gx, gy), layer) for layer in range(len(LAYERS))}

        def heuristic(index):
            x, y = self.point(index)
            return math.hypot(x - gx * GRID, y - gy * GRID)

        open_set = [(heuristic(node[0]), 0.0, node, None) for node in starts]
        heapq.heapify(open_set)
        came, cost = {}, {node: 0.0 for node in starts}
        steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]

        while open_set:
            _, spent, node, previous = heapq.heappop(open_set)
            if node in came:
                continue
            came[node] = previous
            if node in goals:
                path, walk = [], node
                while walk is not None:
                    index, layer = walk
                    path.append((self.point(index), layer))
                    walk = came[walk]
                return path[::-1]

            index, layer = node
            ix, iy = index % self.nx, index // self.nx
            neighbours = []
            for dx, dy in steps:
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < self.nx and 0 <= jy < self.ny:
                    neighbours.append(((self.index(jx, jy), layer), GRID, (dx, dy)))
            if self.via_fits(index, net):
                for other in range(len(LAYERS)):
                    if other != layer:
                        neighbours.append(((index, other), VIA_COST, None))

            for neighbour, step, direction in neighbours:
                if neighbour in came or not self.free(neighbour[0], neighbour[1], net):
                    continue
                if direction and previous is not None and previous[1] == layer:
                    px, py = previous[0] % self.nx, previous[0] // self.nx
                    if (ix - px, iy - py) != direction:
                        step += GRID * 0.6
                new = spent + step
                if new < cost.get(neighbour, math.inf):
                    cost[neighbour] = new
                    heapq.heappush(open_set, (new + heuristic(neighbour[0]), new,
                                              neighbour, node))
        return None

    def occupy(self, path, net):
        for (x, y), layer in path:
            self.stamp(x, y, TRACK_KEEPOUT, net, layer)
        for (before, la), (after, lb) in zip(path, path[1:]):
            if la != lb:
                self.stamp(before[0], before[1],
                           VIA_DIAMETER / 2 + HOLE_CLEARANCE + TRACK_WIDTH / 2, net)


def inside_rounded_rect(x, y, width, height, radius, keep):
    """Is a point far enough inside a rounded rectangle?"""
    left, right = keep, width - keep
    top, bottom = keep, height - keep
    if not (left <= x <= right and top <= y <= bottom):
        return False
    for cx, cy in ((radius, radius), (width - radius, radius),
                   (radius, height - radius), (width - radius, height - radius)):
        near_x = x < radius if cx < width / 2 else x > width - radius
        near_y = y < radius if cy < height / 2 else y > height - radius
        if near_x and near_y:
            return math.hypot(x - cx, y - cy) <= radius - keep
    return True


def simplify(path):
    """Collapse the grid steps into as few straight segments as possible.

    Returns ``(runs, vias)`` -- a run being a list of points on one layer, and
    a via being the point where the path crossed to the other side.
    """
    runs, vias = [], []
    run = [path[0][0]]
    layer = path[0][1]
    for (point, this_layer) in path[1:]:
        if this_layer != layer:
            runs.append((run, layer))
            vias.append(run[-1])
            run, layer = [run[-1]], this_layer
        else:
            run.append(point)
    runs.append((run, layer))

    out = []
    for points, which in runs:
        if len(points) < 2:
            continue
        def heading(a, b):
            """Which way a step went, to 3 decimals.

            Rounded because the points are not: 4.2 - 4.0 and 4.4 - 4.2 are
            different numbers in binary, so an unrounded comparison calls
            every step a corner and emits one segment per grid cell.
            """
            return round(b[0] - a[0], 3), round(b[1] - a[1], 3)

        start = points[0]
        for before, here, after in zip(points, points[1:], points[2:]):
            if heading(before, here) != heading(here, after):
                out.append((start, here, which))
                start = here
        out.append((start, points[-1], which))
    return out, vias


def segments(pieces, vias, net_number):
    text = "".join(
        '\t(segment\n\t\t(start %s %s)\n\t\t(end %s %s)\n\t\t(width %s)\n'
        '\t\t(layer "%s")\n\t\t(net %d)\n\t)\n'
        % (fmt(a[0]), fmt(a[1]), fmt(b[0]), fmt(b[1]), TRACK_WIDTH,
           LAYERS[which], net_number)
        for a, b, which in pieces if a != b
    )
    text += "".join(
        '\t(via\n\t\t(at %s %s)\n\t\t(size %s)\n\t\t(drill %s)\n'
        '\t\t(layers "F.Cu" "B.Cu")\n\t\t(net %d)\n\t)\n'
        % (fmt(x), fmt(y), VIA_DIAMETER, VIA_DRILL, net_number)
        for x, y in vias
    )
    return text


def fmt(value):
    text = ("%.4f" % value).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def spanning_tree(net_pads):
    """The shortest set of links that joins every pad on a net.

    Prim's, on distance.  Two pads give one link; the three-pad nets on this
    board give two, one of which is the short hop across the switch footprint.
    """
    remaining = list(net_pads[1:])
    joined = [net_pads[0]]
    edges = []
    while remaining:
        best = min(((a, b) for a in joined for b in remaining),
                   key=lambda pair: math.dist((pair[0].x, pair[0].y),
                                              (pair[1].x, pair[1].y)))
        edges.append(best)
        joined.append(best[1])
        remaining.remove(best[1])
    return edges


def strip_tracks(text):
    for tag in ("segment", "via"):
        text = strip_tag(text, tag)
    return text


def strip_tag(text, tag):
    while True:
        for start, end in blocks(text, tag):
            line = text.rfind("\n", 0, start) + 1
            tail = end
            while tail < len(text) and text[tail] in "\r\n":
                tail += 1
            text = text[:line] + text[tail:]
            break
        else:
            return text


def main(argv=None):
    here = pathlib.Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcb", type=pathlib.Path,
                        default=here.parent / "layout/default/default.kicad_pcb")
    parser.add_argument("--clear", action="store_true", help="remove the traces")
    args = parser.parse_args(argv)

    text = args.pcb.read_text()
    text = strip_tracks(text)
    if args.clear:
        args.pcb.write_text(text)
        print("removed the traces")
        return 0

    import json

    plan = json.loads((here / "placement.json").read_text())
    board = plan["board"]
    width, height = board["size"]
    pads = read_pads(text)
    holes = [(x + width / 2, height / 2 - y, board["bolt_diameter"] / 2)
             for x, y in plan["bolts"]]

    by_net = {}
    for pad in pads:
        if pad.net_name and pad.net_name != "gnd":
            by_net.setdefault((pad.net_number, pad.net_name), []).append(pad)
    # A net is not two pads.  The compound switch footprint carries the same
    # pole on a Choc pad and an MX pad, so most nets have three, and joining
    # only the first two leaves the third floating -- which is what KiCad was
    # reporting as twenty unconnected nets on a board that looked routed.
    # Each net gets a spanning tree over all of its pads.
    todo = []
    for (number, name), net_pads in by_net.items():
        if len(net_pads) < 2:
            continue
        todo.append(((number, name), spanning_tree(net_pads)))
    # Shortest first.  Routing the hard ones first was tried and is worse:
    # they take long ways round, and then nothing else fits either -- 7 of 23
    # against 17.  Short nets get out of the way; long ones can detour.
    todo.sort(key=lambda item: sum(math.dist((a.x, a.y), (b.x, b.y))
                                   for a, b in item[1]))

    grid = Grid(board, pads, holes)
    routed, failed, added, via_count = 0, [], "", 0
    for (number, name), links in todo:
        ok = True
        for a, b in links:
            path = grid.route((a.x, a.y), (b.x, b.y), number)
            if path is None:
                ok = False
                break
            # Land on the pads, not on the grid cells nearest them: a track
            # that stops 0.1mm short is a track that connects nothing.
            path[0] = ((round(a.x, 4), round(a.y, 4)), path[0][1])
            path[-1] = ((round(b.x, 4), round(b.y, 4)), path[-1][1])
            grid.occupy(path, number)
            pieces, vias = simplify(path)
            added += segments(pieces, vias, number)
            via_count += len(vias)
        if ok:
            routed += 1
        else:
            failed.append(name)

    closing = text.rstrip().rfind("\n)")
    args.pcb.write_text(text[:closing + 1] + added + ")\n")

    print("routed %d of %d nets, %d vias" % (routed, len(todo), via_count))
    if failed:
        print("could not route: %s" % ", ".join(failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
