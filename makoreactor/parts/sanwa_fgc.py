"""Parametric parts for an FGC leverless controller built with Sanwa buttons.

Where :mod:`makoreactor.parts.layered_leverless` stacks five flat plates and
clips mechanical switches into one of them, this assembly is the arcade-parts
equivalent: snap-in buttons in a thin top plate, a thicker plate under it that
does nothing but hold that plate flat, and a printed body carrying everything
that is not flat -- the rear panel, the board mount, and the screw bosses every
plate fastens into::

    SanwaTopPlate       3mm, buttons snap into this
    SanwaSupportPlate   6mm, same holes 4mm wider, stiffens the top plate
    SanwaBody           36mm, printed in two halves: walls, rear panel,
                        board holder, screw bosses
    SanwaBottomPlate    3mm, closes the bottom

The three plates are flat and come off a laser or router as DXF; the body is
the only part that has to be printed, and at 320 x 200mm it does not fit a
printer whole, so it splits down :attr:`SanwaPlate.split_offset` into two
pieces that locate on dowels and are clamped together by the plates.

How it goes together
--------------------

Nothing threads into plastic and nothing is glued.  The printed body takes
brass **M3 heat-set inserts** -- a 4.2mm hole 6mm deep, which is the standard
seat for a 4.6 x 5.7mm insert -- pressed in with a soldering iron before
anything else happens.  Every screw is then an M3 machine screw into brass.

The inserts go in from whichever face the screw comes from, so all of them are
reachable on a bare printed half:

* the rim bosses take one in the **top** face for the two upper plates, and the
  ones the bottom plate uses take a second in the **bottom** face.
* the board holder takes two in its top face.

Then, in order: dowel the two halves together, press the rear buttons and the
jack into the back panel, screw the board up into its standoffs from
underneath, snap the face buttons into the top plate and wire them, lay the
support plate on the body and the top plate on that, and run the long screws
down through both into the rim.  The bottom plate goes on last, from below,
and is the only thing to remove to get at the board again.

:meth:`SanwaAssembly.fasteners` prints the whole schedule with lengths.

Component dimensions
--------------------

The numbers that came off datasheets or panel drawings are collected in
:class:`SnapInButton` and :class:`DSeriesJack` rather than being scattered
through the parts:

* Sanwa OBSF-24/OBSF-30: 24mm and 30mm mounting holes, bezels 3mm wider than
  the hole, panel thickness 2 - 3.9mm for the snap tabs to grip.
* Neutrik D-series (the footprint the panel-mount USB-C jack uses): 24mm bore,
  two 3.2mm screw holes diagonally opposite at (9.5, 12.0) either side of it,
  panel thickness 1 - 3mm.  Taken off a panel maker's XLR cutout template,
  because Neutrik publishes the drawing only as a scan; note that the 24mm
  screw spacing widely repeated on forums cannot be right, as it would put the
  screws inside the bore.
* Brook Gen-5X / UFB: 96.01 x 45.01mm.  Brook does not publish the mounting
  hole pattern, so :attr:`SanwaBody.board_hole_inset` assumes holes 3.5mm in
  from each corner -- **verify**, or print the body and drill the holder.

The plate is 200mm deep rather than the 170mm the button layout needs.  Rear
buttons spread across the whole back wall reach 24.5mm into the case, and the
FGC layout's start/select/home row sits close to the back, so the two would
foul each other on a shallower plate -- :meth:`SanwaAssembly.checks` measures
exactly that.

Because the rear panel has to be thin enough for a snap-in button to grip and
for the jack's screws to reach, but an 8mm printed wall is thicker than that,
the wall is relieved from the inside to
:attr:`SanwaBody.rear_panel_thickness` around each rear component.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

from makoreactor.layouts import FgcPlus, Layout, SanwaFgcLeverless
from makoreactor.parts.layered_leverless import LayeredAssembly, PlatePart, in2mm


@dataclass(frozen=True)
class SnapInButton:
    """A snap-in arcade button, as far as the panel it mounts in is concerned.

    ``below_panel`` is how far the body hangs behind the panel, measured to the
    back of the microswitch.  Spade terminals and wire want roughly another
    10mm behind that, which is why the body is open underneath.
    """

    hole_diameter: float
    bezel_diameter: float
    below_panel: float = 24.5
    panel_min: float = 2.0
    panel_max: float = 3.9

    def fits_panel(self, thickness: float) -> bool:
        return self.panel_min <= thickness <= self.panel_max


#: Sanwa OBSF-24 and OBSF-30, the two buttons this assembly is built around.
OBSF24 = SnapInButton(hole_diameter=24.0, bezel_diameter=27.0)
OBSF30 = SnapInButton(hole_diameter=30.0, bezel_diameter=33.0)


@dataclass(frozen=True)
class DSeriesJack:
    """The Neutrik D-series panel footprint.

    The panel-mount USB-C jack this controller uses is a D-series shell, so it
    drops into the same cutout as an XLR: a 24mm bore with an M3 screw either
    side of it.
    """

    bore: float = 24.0
    screw_diameter: float = 3.2
    #: Screw centres relative to the bore, as ``(across, up)`` pairs.  They sit
    #: diagonally opposite each other, which is why an XLR panel jack always
    #: looks slightly askew.
    screw_offsets: tuple[tuple[float, float], ...] = ((-9.5, 12.0), (9.5, -12.0))
    panel_max: float = 3.0
    #: How far the shell reaches into the case behind the panel.
    depth_behind_panel: float = 30.0

    def envelope(self) -> tuple[float, float]:
        """Width and height of everything the cutout needs, screws included."""
        radius = self.screw_diameter / 2
        across = max([self.bore / 2] + [abs(dx) + radius for dx, _ in self.screw_offsets])
        up = max([self.bore / 2] + [abs(dy) + radius for _, dy in self.screw_offsets])
        return (2 * across, 2 * up)


DSERIES = DSeriesJack()


def _cylinder_y(x: float, z: float, radius: float, y0: float, y1: float) -> cq.Workplane:
    """A cylinder lying along +Y, from ``y0`` to ``y1``, centred on ``(x, z)``.

    Everything in the rear panel is a hole drilled horizontally into a vertical
    wall, which is the one direction the plate-shaped parts never need.
    """
    return (
        cq.Workplane("XY")
        .circle(radius)
        .extrude(y1 - y0)
        .rotate((0, 0, 0), (1, 0, 0), -90)
        .translate((x, y0, z))
    )


def _box_y(x: float, z: float, width: float, height: float, y0: float, y1: float) -> cq.Workplane:
    """A rectangular prism lying along +Y, centred on ``(x, z)``."""
    return (
        cq.Workplane("XY")
        .rect(width, height)
        .extrude(y1 - y0)
        .rotate((0, 0, 0), (1, 0, 0), -90)
        .translate((x, y0, z))
    )


def _cylinder_x(y: float, z: float, radius: float, x0: float, x1: float) -> cq.Workplane:
    """A cylinder lying along +X, from ``x0`` to ``x1``, centred on ``(y, z)``."""
    return (
        cq.Workplane("XY")
        .circle(radius)
        .extrude(x1 - x0)
        .rotate((0, 0, 0), (0, 1, 0), 90)
        .translate((x0, y, z))
    )


def _merge(solids) -> cq.Workplane:
    merged = None
    for solid in solids:
        merged = solid if merged is None else merged.union(solid)
    return merged


@dataclass
class SanwaPlate(PlatePart):
    """A part of the Sanwa stack, and the parameters the whole stack shares.

    Every part is cut or printed to the same outline and fastened on the same
    screw pattern, so the pattern has to be derived identically by all of them.
    That is why this class carries more than a plate strictly needs: where a
    screw can go along the back edge depends on what is mounted in the back
    wall, and two of the screws land on the board holder, so the rear panel and
    board spec live here rather than on :class:`SanwaBody` alone.  Each part
    then uses the subset it needs, and ``LayeredAssembly.set`` keeps them in
    step.

    The inherited ``hole_offset`` / ``hole_deltax`` / ``hole_deltay`` fields are
    unused; ``screw_inset`` and ``screw_pitch`` take their place.
    """

    #: Cut flat from sheet, so DXF and SVG exports mean something.  Not a
    #: dataclass field: it describes the part, it does not parameterise it.
    flat = True

    width: float = 320.0
    height: float = 200.0
    depth: float = 3.0
    #: M3 clearance.
    hole_diameter: float = 3.4
    fillet_radius: float = 12.0
    #: The outline is a rectangle with its corners cut off rather than rounded
    #: -- ``corner_chamfer`` is how much is taken off along each edge, and
    #: ``corner_fillet`` softens the two vertices that leaves.
    corner_chamfer: float = 20.0
    corner_fillet: float = 5.0

    #: Screw centres, in from the plate edge.
    screw_inset: float = 8.0
    #: Screws are spread along each edge no further apart than this.
    screw_pitch: float = 120.0
    #: The bottom plate only has to stay put -- nothing pushes on it and it
    #: carries no buttons -- so it takes a subset of the rim, no two of its
    #: screws further apart than this round the perimeter.  Every screw it
    #: skips is a heat-set insert saved as well.
    bottom_screw_pitch: float = 170.0
    layout: Layout = field(default_factory=SanwaFgcLeverless)

    #: Wall and boss of the printed body.  Shared because they set how much
    #: room a screw needs in the back wall.
    wall_thickness: float = 8.0
    #: Screw bosses.  Modest, because with six rear buttons a boss has to fit
    #: in the bay between two of them; the wall it merges into carries the
    #: load, and at this inset half the boss is buried in it.
    boss_diameter: float = 11.5

    #: Rear panel.  The jack sits in the middle and the buttons are split
    #: evenly either side of it, ``rear_button_gap`` out from the centre and
    #: then every ``rear_button_pitch``.  Set ``rear_button_count`` to 6 for
    #: three a side; the pitch closes up on its own if the default would run
    #: the outermost button off the end of the wall.
    rear_button: SnapInButton = OBSF24
    rear_button_count: int = 4
    rear_button_gap: float = 36.0
    rear_button_pitch: float = None
    rear_button_max_pitch: float = 46.0
    rear_relief_clearance: float = 4.0
    #: Slots either side of every rear button, so the snap tabs can be pinched
    #: from outside and the button pushed back out.  A button mounted in a wall
    #: has its tabs behind that wall, and once the case is closed there is no
    #: reaching them any other way.  ``tab_slot_width`` is how far the slot
    #: reaches past the hole; the bezel covers the first
    #: ``bezel_clearance / 2`` of it.
    tab_slot_width: float = 3.0
    tab_slot_height: float = 12.0
    usb_jack: DSeriesJack = DSERIES
    usb_offset: float = 0.0
    usb_relief_clearance: float = 2.0
    #: Wall left either side of a rear screw boss, so it does not break into
    #: the relief pocket next to it.
    rear_screw_margin: float = 1.0

    #: Where the body is cut in two for printing.  Left at ``None`` it lands in
    #: the middle of the clear bay beside the jack, which moves whenever the
    #: rear panel does; set it to pin the split somewhere specific.
    split_offset: float = None

    #: Brook board, hung under the top of the cavity.  ``board_screw_offsets``
    #: are relative to ``board_center`` and carry the two screws that tie the
    #: top plates down in the middle of their span.
    board_size: tuple[float, float] = (96.01, 45.01)
    board_center: tuple[float, float] = (-80.0, -48.0)
    board_screw_offsets: tuple[tuple[float, float], ...] = ((-30.0, 23.0), (30.0, 23.0))

    # --- screw pattern ----------------------------------------------------

    # --- outline ----------------------------------------------------------

    def profile_points(self, inset: float = 0.0, chamfer: float = None) -> list[tuple[float, float]]:
        """The outline as a polygon, optionally offset ``inset`` inwards.

        Offsetting a 45-degree chamfer inwards shortens it: the two edges it
        spans each come in by ``inset``, but the chamfer itself only moves in
        by ``inset * sqrt(2)``, which leaves ``inset * (2 - sqrt(2))`` less of
        it.
        """
        x = self.width / 2 - inset
        y = self.height / 2 - inset
        chamfer = self.corner_chamfer if chamfer is None else chamfer
        cut = max(chamfer - inset * (2 - math.sqrt(2)), 0.0)
        if cut <= 0:
            return [(x, y), (x, -y), (-x, -y), (-x, y)]
        return [
            (x - cut, y), (x, y - cut), (x, -(y - cut)), (x - cut, -y),
            (-(x - cut), -y), (-x, -(y - cut)), (-x, y - cut), (-(x - cut), y),
        ]

    def prism(self, depth: float, inset: float = 0.0, chamfer: float = None,
              fillet: float = None) -> cq.Workplane:
        """The outline, extruded ``depth`` and rounded at every corner."""
        solid = (
            cq.Workplane("XY")
            .polyline(self.profile_points(inset, chamfer))
            .close()
            .extrude(depth)
        )
        radius = (self.corner_fillet - inset) if fillet is None else fillet
        if radius > 0:
            try:
                solid = solid.edges("|Z").fillet(radius)
            except Exception:
                pass  # too tight for this radius; leave the corners sharp
        return solid

    def blank(self) -> cq.Workplane:
        return self.prism(self.depth)

    def straight_half(self, axis: str = "x", inset: float = 0.0) -> float:
        """Half the length of a straight edge, chamfers excluded.

        The chamfers take a bite out of both ends of every edge, so this is
        what is actually available to put screws or components on.
        """
        points = self.profile_points(inset)
        limit = (self.height if axis == "x" else self.width) / 2 - inset
        index, other = (0, 1) if axis == "x" else (1, 0)
        return max(abs(p[index]) for p in points if abs(abs(p[other]) - limit) < 1e-9)

    def rear_pitch(self) -> float:
        """Spacing between rear buttons on one side of the jack."""
        if self.rear_button_pitch is not None:
            return float(self.rear_button_pitch)

        per_side = self.rear_button_count // 2
        if per_side < 2:
            return self.rear_button_max_pitch

        # As wide as will fit on the straight part of the wall.  Left at that,
        # six buttons pack tightly enough to squeeze out the screws between
        # them, so the wall keeps whichever is smaller.
        edge = self.straight_half("x") - 2 * self.rear_screw_margin
        room = edge - self._rear_span_radius() - self.rear_button_gap
        return min(self.rear_button_max_pitch, room / (per_side - 1))

    def _rear_relief_radius(self) -> float:
        return (self.rear_button.hole_diameter + self.rear_relief_clearance) / 2

    def _rear_span_radius(self) -> float:
        """How much wall a rear button needs, relief or tab slots, whichever
        reaches further."""
        return max(
            self._rear_relief_radius(),
            self.rear_button.hole_diameter / 2 + self.tab_slot_width,
        )

    def rear_button_points(self) -> list[float]:
        """X centres of the rear buttons, evenly either side of the jack."""
        pitch = self.rear_pitch()
        per_side = self.rear_button_count // 2
        offsets = [self.rear_button_gap + i * pitch for i in range(per_side)]
        return sorted([self.usb_offset - o for o in offsets]
                      + [self.usb_offset + o for o in offsets])

    def rear_spans(self) -> list[tuple[float, float]]:
        """How much of the back wall each rear component needs, as x spans.

        Measured on the relieved opening rather than the hole, because that is
        the footprint that has to land on plain wall.
        """
        radius = self._rear_span_radius()
        spans = [(x - radius, x + radius) for x in self.rear_button_points()]
        jack_half = (self.usb_jack.envelope()[0] + self.usb_relief_clearance) / 2
        spans.append((self.usb_offset - jack_half, self.usb_offset + jack_half))
        return sorted(spans)

    def split_x(self) -> float:
        """Where the body is cut in two.

        It cannot go down the centreline -- the jack is there -- and it has to
        stay near it, or one half stops fitting the bed.  That leaves the bay
        between the jack and the first button on either side, so the split
        takes the middle of it.
        """
        if self.split_offset is not None:
            return float(self.split_offset)

        spans = self.rear_spans()
        beside = [(start, end) for start, end in spans if start > self.usb_offset]
        jack = max(end for start, end in spans if start <= self.usb_offset <= end)
        if not beside:
            return (jack + self.straight_half("x", self.screw_inset)) / 2
        return (jack + min(start for start, _ in beside)) / 2

    def rear_screw_points(self) -> list[float]:
        """X positions for the screws along the back edge.

        The back edge cannot take an evenly spaced row: the jack and the
        buttons are in the way, and a button's body reaches 24.5mm past the
        wall, so a boss behind one would be inside it.  Every bay between rear
        components wide enough for a boss gets one, and the bay the split runs
        through is left out -- along with the one opposite it, to keep the
        pattern symmetric.

        Unlike the other three edges this one is not screwed at its ends: with
        six buttons the outermost reaches too far along the wall to leave room
        there, and the corner is picked up by the side edge instead.
        """
        limit = self.straight_half("x", self.screw_inset)
        boss = self.boss_diameter / 2 + self.rear_screw_margin
        needed = 2 * boss

        blocked = list(self.rear_spans())
        for centre in (-self.split_x(), self.split_x()):
            blocked.append((centre - boss - 2, centre + boss + 2))

        points = []
        for low, high in _free_spans(blocked, -limit, limit):
            width = high - low
            if width < needed:
                continue
            count = max(1, int(width // self.screw_pitch))
            step = width / (count + 1)
            points += [low + step * (i + 1) for i in range(count)]
        return sorted(points)

    def corner_screw_points(self) -> list[tuple[float, float]]:
        """One screw on each chamfer, rather than one either side of it.

        The chamfer is a face like any other, and a screw in the middle of it
        pulls the corner down on the diagonal it actually wants pulling.  Two
        screws flanking it hold the same corner twice.
        """
        half = self.corner_chamfer / 2 + self.screw_inset / math.sqrt(2)
        return [
            (sx * (self.width / 2 - half), sy * (self.height / 2 - half))
            for sx in (-1, 1) for sy in (-1, 1)
        ]

    def mounting_points(self) -> list[tuple[float, float]]:
        """Screws round the perimeter, following the chamfered outline in.

        One on every chamfer, then as many along each straight edge as it takes
        to keep the spacing under :attr:`screw_pitch`.  The back edge is the
        exception: what is mounted in it decides where a screw can go at all.
        """
        x = self.width / 2 - self.screw_inset
        y = self.height / 2 - self.screw_inset
        along_x = self.straight_half("x", self.screw_inset)
        along_y = self.straight_half("y", self.screw_inset)

        def between(half: float) -> list[float]:
            """Points along an edge, excluding its ends -- the chamfers have
            those covered."""
            steps = max(math.ceil(2 * half / self.screw_pitch), 1)
            return [-half + 2 * half * i / steps for i in range(1, steps)]

        points = self.corner_screw_points()
        points += [(px, -y) for px in between(along_x)]
        points += [(px, y) for px in self.rear_screw_points()]
        points += [(sx, py) for py in between(along_y) for sx in (-x, x)]
        return list(dict.fromkeys(points))

    def bottom_screw_points(self) -> list[tuple[float, float]]:
        """The subset of the rim the bottom plate uses.

        Walks the rim in perimeter order and keeps a screw whenever the last
        one it kept is more than :attr:`bottom_screw_pitch` behind, so the
        spacing stays even however the rim came out.  The chamfers are always
        kept: they are the corners.
        """
        corners = set(self.corner_screw_points())
        # Explicitly the rim pattern, not self.mounting_points(): the bottom
        # plate's own is this subset, and would recurse.
        rim = sorted(SanwaPlate.mounting_points(self), key=lambda p: math.atan2(p[1], p[0]))
        if not rim:
            return []

        start = next((i for i, p in enumerate(rim) if p in corners), 0)
        rim = rim[start:] + rim[:start]

        # Keep a screw when dropping it would leave too big a gap to the next
        # one along -- looking ahead rather than behind, so that skipping is
        # never what causes the gap.
        kept = [rim[0]]
        for point, following in zip(rim[1:], rim[2:] + rim[:1]):
            if point in corners or math.dist(kept[-1], following) > self.bottom_screw_pitch:
                kept.append(point)
        return kept

    def board_screw_points(self) -> list[tuple[float, float]]:
        """The screws that land on the board holder rather than the rim."""
        cx, cy = self.board_center
        return [(cx + dx, cy + dy) for dx, dy in self.board_screw_offsets]

    def _cut_buttons(self, plate: cq.Workplane, oversize: float = 0.0) -> cq.Workplane:
        """Cut the button openings, every hole grown by ``oversize``."""
        holes = (
            self.layout.button_geom(oversize)
            .extrude(self.depth * 3)
            .translate((0, 0, -self.depth))
        )
        return plate.cut(holes)


@dataclass
class SanwaTopPlate(SanwaPlate):
    """The plate the buttons snap into.

    Its thickness is not a free choice: the snap tabs only grip a panel between
    :attr:`SnapInButton.panel_min` and :attr:`SnapInButton.panel_max`, so this
    plate stays at 3mm however thick the rest of the stack gets.  It also picks
    up the two screws over the board holder, which is what keeps the middle of
    a 320mm span from lifting.
    """

    depth: float = 3.0

    def mounting_points(self) -> list[tuple[float, float]]:
        return super().mounting_points() + self.board_screw_points()

    def generate(self) -> cq.Workplane:
        return self._cut_buttons(self._cut_mounting_holes(self.blank()))


@dataclass
class SanwaSupportPlate(SanwaPlate):
    """The plate under the top plate: same outline, same screws, wider holes.

    A 3mm plate spanning 320mm would flex under a hand; this one is thick
    enough to stop that.  It takes no part in holding the buttons, so its
    openings are :attr:`button_clearance` wider on diameter -- enough to clear
    the button bodies and their snap tabs, while still leaving a seat under the
    top plate right up to the edge of every hole.

    The openings are meant to be generous: a snap-in button is released by
    pinching the two tabs behind it, and with a narrow ring of plate around
    each hole there is nothing to get a finger or a screwdriver onto.  So they
    are allowed to run into each other and merge into one pocket per cluster
    -- the plate does not need a web between every pair of buttons, it needs to
    come out in one piece and still carry the top plate at its rim.

    That is the real limit, and it is a cliff rather than a slope: openings
    merge harmlessly until about 9mm of clearance on this layout, and at 9.5mm
    the plate sheds the islands between three merged openings and comes out in
    three pieces.  :attr:`max_merge` is the guard, set a millimetre back from
    where that happens; ``test_every_part_is_one_valid_solid`` is what proves
    it, by building the thing.
    """

    depth: float = 6.0
    #: Added to each button hole diameter.  8mm makes every opening 32mm
    #: around a 24mm button, which is a finger's worth of access.
    button_clearance: float = 8.0
    #: How far neighbouring openings may run into each other.  Past this the
    #: plate starts losing the material between them.
    max_merge: float = 3.0

    def mounting_points(self) -> list[tuple[float, float]]:
        return super().mounting_points() + self.board_screw_points()

    def generate(self) -> cq.Workplane:
        plate = self._cut_mounting_holes(self.blank())
        return self._cut_buttons(plate, self.button_clearance)


@dataclass
class SanwaBottomPlate(SanwaPlate):
    """Solid bottom: outline and screw holes, screwed up into the body.

    It fastens on the rim only -- the board holder is at the top of the cavity,
    out of its reach -- and it lands on the body's skirt rather than on bare
    wall, which is what lets it stay a plain 3mm cut plate.
    """

    depth: float = 3.0

    def mounting_points(self) -> list[tuple[float, float]]:
        return self.bottom_screw_points()

    def generate(self) -> cq.Workplane:
        return self._cut_mounting_holes(self.blank())


@dataclass
class SanwaBody(SanwaPlate):
    """The printed middle: walls, rear panel, board holder, screw bosses.

    Height is set by the rear panel rather than by what has to fit inside.  A
    24mm button needs its 24mm hole plus a ring of wall around it for the snap
    tabs to bear on, and that ring has to clear the plate seats top and bottom,
    which puts the wall at 36mm.  The face buttons only reach
    :attr:`SnapInButton.below_panel` behind the top plate, so that height also
    leaves the bottom of the cavity clear for the wiring.

    The bottom is open: the bottom plate closes it.  The board hangs from the
    top of the cavity instead, on a holder that also carries two of the top
    plates' screws, so the board comes out from underneath without disturbing
    the button plates.

    :meth:`halves` cuts the part in two down :attr:`split_offset` for printing.
    The two pieces locate on dowels through the front and back walls and are
    clamped together by the plates that screw into both of them.
    """

    #: Printed, not cut: a flat projection of this part is not a useful export.
    flat = False

    depth: float = 36.0

    #: M3 heat-set insert.
    insert_diameter: float = 4.2
    insert_depth: float = 6.0

    #: The wall is relieved from the inside to this thickness around every rear
    #: component, so snap tabs can grip and the jack's screws can reach.
    rear_panel_thickness: float = 3.0
    #: Full-thickness wall left above and below any relief.
    rear_relief_rim: float = 2.0
    #: Longest stretch of back edge allowed between two screws.  The rear
    #: components decide where screws can go, so this is the constraint that
    #: notices when a crowded back panel has left the edge unsupported.
    rear_span_limit: float = 200.0

    #: Board holder, hanging under the top of the cavity.  The board screws up
    #: into the standoffs from below; the top plates screw down into the slab.
    board_holder_thickness: float = 8.0
    board_holder_margin: float = 8.0
    #: The pad over the board is an island; this is the neck that joins it to
    #: the nearest wall.  Narrow, because on a two-handed board the only way
    #: out to a wall is the corridor between the two thumb clusters.
    board_neck_width: float = 40.0
    board_standoff: float = 6.0
    #: Assumed, not published: mounting holes this far in from each corner.
    board_hole_inset: float = 3.5
    board_post_diameter: float = 7.0
    #: Pilot for an M3 self-tapping screw.
    board_pilot_diameter: float = 2.5

    #: Skirt: a flange turned inwards round the bottom of the walls.  The body
    #: is open underneath, which leaves the two printed halves floppy and the
    #: bottom plate spanning unsupported; this ties the walls together, gives
    #: the plate something to land on all the way round, and puts a wide flat
    #: face on the bed if the part is printed the right way up.  Its opening is
    #: the outline's treatment at a larger scale: a rectangle with the corners
    #: chamfered off and those chamfers rounded.
    skirt_width: float = 16.0
    skirt_depth: float = 3.5
    skirt_chamfer: float = 45.0
    skirt_fillet: float = 10.0

    #: Dowels locating the two printed halves.
    join_pin_diameter: float = 4.0
    join_pin_depth: float = 5.0
    #: What the halves have to fit on.
    print_bed: tuple[float, float] = (220.0, 220.0)

    def part_depth(self) -> float:
        return self.depth

    def rear_boss_points(self) -> list[float]:
        """X centres of the screw bosses standing in the back wall."""
        edge = self.height / 2 - self.screw_inset
        return [x for x, y in self.mounting_points() if abs(y - edge) < 1e-9]

    def _cavity(self) -> cq.Workplane:
        """The cavity follows the outline in, so the wall is an even thickness
        the whole way round, chamfers included."""
        return self.prism(
            self.depth * 3,
            inset=self.wall_thickness,
            fillet=max(self.corner_fillet - self.wall_thickness, 1.0),
        ).translate((0, 0, -self.depth))

    def _bosses(self) -> cq.Workplane:
        return (
            cq.Workplane("XY")
            .pushPoints(self.mounting_points())
            .circle(self.boss_diameter / 2)
            .extrude(self.depth)
            .intersect(self.blank())
        )

    def _insert_holes(self) -> cq.Workplane:
        """Blind holes for heat-set inserts: both ends of every rim boss, and
        the top of the board holder."""
        radius = self.insert_diameter / 2
        below = (
            cq.Workplane("XY")
            .pushPoints(self.bottom_screw_points())
            .circle(radius)
            .extrude(self.insert_depth)
        )
        above = (
            cq.Workplane("XY", origin=(0, 0, self.depth - self.insert_depth))
            .pushPoints(self.mounting_points() + self.board_screw_points())
            .circle(radius)
            .extrude(self.insert_depth)
        )
        return below.union(above)

    def _rear_panel(self) -> cq.Workplane:
        """Everything cut out of the back wall, as one solid to subtract."""
        outer = self.height / 2
        inner = outer - self.wall_thickness
        # Through cuts overshoot the wall in both directions; reliefs stop
        # short of the outer face, leaving `rear_panel_thickness` of material.
        through = (inner - 1.0, outer + 1.0)
        relief = (inner - 1.0, outer - self.rear_panel_thickness)
        z = self.depth / 2

        cuts = []
        slot_offset = self.rear_button.hole_diameter / 2 + self.tab_slot_width / 2
        for x in self.rear_button_points():
            cuts.append(_cylinder_y(x, z, self.rear_button.hole_diameter / 2, *through))
            cuts.append(_cylinder_y(x, z, self._rear_relief_radius(), *relief))
            # The release slots run right up to the hole, so a screwdriver can
            # follow the wall in and reach the tab behind it.
            for side in (-1, 1):
                cuts.append(_box_y(
                    x + side * slot_offset, z,
                    self.tab_slot_width, self.tab_slot_height, *through,
                ))

        jack = self.usb_jack
        cuts.append(_cylinder_y(self.usb_offset, z, jack.bore / 2, *through))
        for dx, dz in jack.screw_offsets:
            cuts.append(
                _cylinder_y(self.usb_offset + dx, z + dz, jack.screw_diameter / 2, *through)
            )
        jack_width, jack_height = jack.envelope()
        cuts.append(
            _box_y(
                self.usb_offset,
                z,
                jack_width + self.usb_relief_clearance,
                jack_height + self.usb_relief_clearance,
                *relief,
            )
        )
        return _merge(cuts)

    def board_hole_points(self) -> list[tuple[float, float]]:
        """Where the board's standoffs hang.  See ``board_hole_inset``."""
        cx, cy = self.board_center
        dx = self.board_size[0] / 2 - self.board_hole_inset
        dy = self.board_size[1] / 2 - self.board_hole_inset
        return [(cx + sx * dx, cy + sy * dy) for sx in (-1, 1) for sy in (-1, 1)]

    def board_holder_extent(self) -> tuple[float, float, float, float]:
        """The pad the board hangs from, ``(x0, y0, x1, y1)``."""
        cx, cy = self.board_center
        bw, bh = self.board_size
        margin = self.board_holder_margin
        return (cx - bw / 2 - margin, cy - bh / 2 - margin,
                cx + bw / 2 + margin, cy + bh / 2 + margin)

    def board_neck_extent(self) -> tuple[float, float, float, float]:
        """The strip joining that pad to the front wall.

        A pad floating in the middle of the cavity would print, but not as one
        piece with the body, so it has to reach a wall somewhere.  It goes
        forwards: the back wall is full of buttons whose bodies reach into the
        same space.
        """
        cx, _ = self.board_center
        _, y0, _, _ = self.board_holder_extent()
        half = self.board_neck_width / 2
        return (cx - half, -(self.height / 2 - self.wall_thickness / 2), cx + half, y0)

    def _board_holder(self) -> cq.Workplane:
        top = self.depth - self.board_holder_thickness

        def slab_of(extent):
            x0, y0, x1, y1 = extent
            return (
                cq.Workplane("XY", origin=(0, 0, top))
                .center((x0 + x1) / 2, (y0 + y1) / 2)
                .rect(x1 - x0, y1 - y0)
                .extrude(self.board_holder_thickness)
            )

        slab = (
            slab_of(self.board_holder_extent())
            .union(slab_of(self.board_neck_extent()))
            .intersect(self.blank())
        )
        standoffs = (
            cq.Workplane("XY", origin=(0, 0, top - self.board_standoff))
            .pushPoints(self.board_hole_points())
            .circle(self.board_post_diameter / 2)
            .extrude(self.board_standoff)
        )
        return slab.union(standoffs)

    def skirt_opening(self) -> float:
        """How far in from the plate edge the skirt's opening starts."""
        return self.wall_thickness + self.skirt_width

    def _skirt(self) -> cq.Workplane:
        """The flange itself: the cavity footprint at the bottom, less the
        opening left in the middle of it."""
        flange = self.prism(self.skirt_depth, inset=self.wall_thickness)
        opening = self.prism(
            self.skirt_depth * 3,
            inset=self.skirt_opening(),
            chamfer=self.skirt_chamfer,
            fillet=self.skirt_fillet,
        ).translate((0, 0, -self.skirt_depth))
        return flange.cut(opening)

    def _board_pilots(self) -> cq.Workplane:
        """Pilot holes up through the standoffs into the slab."""
        bottom = self.depth - self.board_holder_thickness - self.board_standoff
        return (
            cq.Workplane("XY", origin=(0, 0, bottom))
            .pushPoints(self.board_hole_points())
            .circle(self.board_pilot_diameter / 2)
            .extrude(self.board_standoff + self.board_holder_thickness / 2)
        )

    def _join_pins(self) -> cq.Workplane:
        """Dowel holes across the split, in the front and back walls."""
        x0 = self.split_x() - self.join_pin_depth
        x1 = self.split_x() + self.join_pin_depth
        z = self.depth / 2
        wall = self.height / 2 - self.wall_thickness / 2
        return _merge([
            _cylinder_x(y, z, self.join_pin_diameter / 2, x0, x1) for y in (-wall, wall)
        ])

    def generate(self) -> cq.Workplane:
        body = self.blank().cut(self._cavity())
        body = body.union(self._bosses())
        body = body.union(self._board_holder())
        body = body.union(self._skirt())
        body = body.cut(self._board_pilots())
        body = body.cut(self._insert_holes())
        body = body.cut(self._rear_panel())
        return body.cut(self._join_pins())

    def halves(self, body: cq.Workplane = None) -> tuple[cq.Workplane, cq.Workplane]:
        """The body cut in two for printing, as ``(left, right)``.

        Pass ``body`` to split a solid that has already been generated.
        """
        body = self.generate() if body is None else body
        reach = 2 * max(self.width, self.height, self.depth)
        keep = (
            cq.Workplane("XY")
            .box(reach, reach, reach)
            .translate((self.split_x() - reach / 2, 0, self.depth / 2))
        )
        return body.intersect(keep), body.cut(keep)


@dataclass
class SanwaAssembly(LayeredAssembly):
    """The Sanwa stack, with the fit checks the design has to satisfy.

    Most of this assembly's dimensions depend on each other -- plate thickness
    on what a snap tab can grip, body height on the rear button, layout scale
    on the bezel diameter, where the screws go on what is mounted in the back
    wall -- so changing one number in isolation tends to break something at the
    other end of the stack.  :meth:`check` states those dependencies as
    assertions, and the CLI and tests run it.
    """

    def checks(self) -> list[tuple[bool, str]]:
        """Every fit constraint, as ``(ok, description)``."""
        top = self.part(SanwaTopPlate)
        support = self.part(SanwaSupportPlate)
        body = self.part(SanwaBody)
        bottom = self.part(SanwaBottomPlate)
        layout = top.layout
        boss = body.boss_diameter / 2
        results = []

        def check(ok, fmt, *args):
            results.append((bool(ok), fmt % args))

        # Snap-in buttons only grip a panel in a narrow thickness band, and
        # both the top plate and the printed rear panel are such a panel.
        face = OBSF30 if OBSF30.hole_diameter in layout.hole_diameters.values() else OBSF24
        check(
            face.fits_panel(top.depth),
            "top plate %.2fmm is within the %.1f-%.1fmm a snap-in button grips",
            top.depth, face.panel_min, face.panel_max,
        )
        check(
            body.rear_button.fits_panel(body.rear_panel_thickness),
            "rear panel %.2fmm is within the %.1f-%.1fmm a snap-in button grips",
            body.rear_panel_thickness, body.rear_button.panel_min, body.rear_button.panel_max,
        )
        check(
            body.rear_panel_thickness <= body.usb_jack.panel_max,
            "rear panel %.2fmm is no thicker than the %.1fmm the jack's screws reach",
            body.rear_panel_thickness, body.usb_jack.panel_max,
        )

        # The face buttons: bezels must not touch each other, the plate edge,
        # or a screw; and their bodies must not reach the bottom plate.
        buttons = layout.buttons()
        gap = _min_bezel_gap(buttons, layout.bezel_clearance)
        check(gap > 0, "closest two bezels clear each other by %.2fmm", gap)

        edge = _min_edge_gap(buttons, layout.bezel_clearance, top.width, top.height)
        check(edge > 0, "closest bezel clears the plate edge by %.2fmm", edge)

        screw = _min_screw_gap(buttons, layout.bezel_clearance, top, boss)
        check(screw > 0, "closest bezel clears a screw boss by %.2fmm", screw)

        held = min(_outline_gap(top, point) for point in top.mounting_points())
        check(
            held - boss > 0,
            "every screw sits in material, the tightest with %.1fmm to spare "
            "past its boss",
            held - boss,
        )

        # Negative here means the openings have merged, which is allowed and
        # is the point -- what is not allowed is merging so far that the plate
        # loses the material between them.
        web = _min_bezel_gap(layout.buttons(support.button_clearance), 0.0)
        merge = -min(web, 0.0)
        check(
            merge <= support.max_merge,
            "support plate openings merge by %.2fmm of the %.2fmm that costs it a piece",
            merge, support.max_merge,
        )

        opening_screw = _min_screw_gap(
            layout.buttons(support.button_clearance), 0.0, support, boss)
        check(
            opening_screw > 0,
            "widened openings clear the screws by %.2fmm", opening_screw,
        )

        reach = face.below_panel - top.depth - support.depth
        check(
            reach < body.depth,
            "face buttons reach %.1fmm into the %.0fmm body, %.1fmm clear of the bottom plate",
            reach, body.depth, body.depth - reach,
        )

        # The rear panel: the wall has to be tall enough for a button hole plus
        # the relieved ring the snap tabs bear on, and the same for the jack.
        rim = body.rear_relief_rim
        relief = body.rear_button.hole_diameter + body.rear_relief_clearance
        check(
            relief + 2 * rim <= body.depth,
            "rear button relief %.1fmm leaves %.1fmm of full-thickness wall above and below it",
            relief, (body.depth - relief) / 2,
        )
        jack_relief = body.usb_jack.envelope()[1] + body.usb_relief_clearance
        check(
            jack_relief + 2 * rim <= body.depth,
            "jack relief %.1fmm leaves %.1fmm of full-thickness wall above and below it",
            jack_relief, (body.depth - jack_relief) / 2,
        )

        slot_show = (body.rear_button.hole_diameter / 2 + body.tab_slot_width
                     - body.rear_button.bezel_diameter / 2)
        check(
            slot_show < body.tab_slot_width,
            "tab slots reach %.1fmm past the bezel that covers them",
            max(slot_show, 0.0),
        )
        check(
            body.tab_slot_height + 2 * body.rear_relief_rim <= body.depth,
            "tab slots leave %.1fmm of wall above and below them",
            (body.depth - body.tab_slot_height) / 2,
        )

        rear_gap = _min_rear_gap(body)
        check(rear_gap > 0, "closest two rear components clear each other by %.2fmm", rear_gap)
        boss_gap = _min_rear_boss_gap(body)
        check(boss_gap > 0, "closest rear component clears a screw boss by %.2fmm", boss_gap)
        rear_face = _min_rear_face_gap(body, buttons, layout.bezel_clearance, reach)
        check(
            rear_face > 0,
            "rear component bodies clear the face buttons hanging above them by %.1fmm",
            rear_face,
        )
        spans = body.rear_spans()
        reach = max(abs(spans[0][0]), abs(spans[-1][1]))
        check(
            reach < body.straight_half("x"),
            "rear components stay %.1fmm clear of where the wall chamfers away",
            body.straight_half("x") - reach,
        )
        unsupported = _widest_rear_span(body)
        check(
            unsupported <= body.rear_span_limit,
            "back edge is screwed down at least every %.0fmm",
            unsupported,
        )

        # The board hangs from the top of the cavity, so it has to be clear of
        # the face buttons in plan rather than under them.
        holder = body.board_holder_extent()
        board = _board_extent(body)
        under = min(
            _min_rect_button_gap(buttons, layout.bezel_clearance, rect)
            for rect in (holder, body.board_neck_extent())
        )
        check(under > 0, "board holder clears every button hanging beside it by %.1fmm", under)

        corners = [(x, y) for x in (board[0], board[2]) for y in (board[1], board[3])]
        inside = min(_outline_gap(body, corner, body.wall_thickness) for corner in corners)
        check(inside > 0, "board sits %.1fmm inside the cavity wall", inside)

        rear_holder = _min_rear_holder_gap(body)
        check(
            rear_holder > 0,
            "board holder clears the rear component bodies by %.1fmm",
            rear_holder,
        )

        drop = body.board_holder_thickness + body.board_standoff
        check(
            drop + 12.0 < body.depth,
            "board hangs %.0fmm below the top of the cavity, %.0fmm clear of the bottom plate",
            drop, body.depth - drop,
        )
        seated = all(
            holder[0] < x < holder[2] and holder[1] < y < holder[3]
            for x, y in body.board_screw_points()
        )
        check(seated, "both middle screws land on the board holder")
        post_gap = min(
            math.hypot(sx - px, sy - py)
            - body.insert_diameter / 2 - body.board_post_diameter / 2
            for sx, sy in body.board_screw_points()
            for px, py in body.board_hole_points()
        )
        check(post_gap > 0, "middle screws clear the board standoffs by %.1fmm", post_gap)

        # The skirt reinforces the open bottom, but it also narrows the only
        # way in: the board goes up through it from underneath.
        through = min(
            _outline_gap(body, corner, body.skirt_opening())
            for corner in [(x, y) for x in (board[0], board[2]) for y in (board[1], board[3])]
        )
        check(through > 0, "board passes through the skirt opening with %.1fmm to spare", through)

        relief_bottom = body.depth / 2 - body._rear_relief_radius()
        check(
            body.skirt_depth <= relief_bottom,
            "skirt stops %.1fmm below the rear button reliefs",
            relief_bottom - body.skirt_depth,
        )
        check(
            body.skirt_width > body.boss_diameter / 2,
            "skirt reaches %.1fmm past the screw bosses it ties together",
            body.skirt_width - body.boss_diameter / 2,
        )

        # Splitting the body for printing.
        split_gap = _min_split_gap(body)
        check(split_gap > 0, "split runs %.1fmm clear of anything in the back wall", split_gap)
        check(
            body.join_pin_depth < split_gap + body.join_pin_diameter / 2,
            "dowel holes stay in solid wall (%.1fmm deep into %.1fmm of clearance)",
            body.join_pin_depth, split_gap,
        )
        boss_split = min(
            abs(x - body.split_x()) for x, _ in body.mounting_points()
        ) - boss
        check(boss_split > 0, "split misses every screw boss by %.1fmm", boss_split)
        check(
            not holder[0] < body.split_x() < holder[2],
            "split does not cut the board holder",
        )
        pieces = _half_sizes(body)
        fits = all(
            max(w, h) <= max(body.print_bed) and min(w, h) <= min(body.print_bed)
            for w, h in pieces
        )
        check(
            fits,
            "printed halves are %s, both inside a %.0f x %.0fmm bed",
            " and ".join("%.0fx%.0f" % piece for piece in pieces), *body.print_bed,
        )

        # Everything fastens to the body, so the patterns have to line up.
        rim_pattern = sorted(body.mounting_points())
        low = bottom.mounting_points()
        check(
            set(low) <= set(rim_pattern),
            "bottom plate's %d screws all land on bosses the rim already has", len(low),
        )
        check(
            set(body.corner_screw_points()) <= set(low),
            "bottom plate is screwed at all four corners",
        )
        loop = sorted(low, key=lambda p: math.atan2(p[1], p[0]))
        widest = max(math.dist(a, b) for a, b in zip(loop, loop[1:] + loop[:1]))
        check(
            widest <= bottom.bottom_screw_pitch * 1.5,
            "bottom plate's screws are never more than %.0fmm apart", widest,
        )
        check(
            sorted(top.mounting_points()) == sorted(support.mounting_points())
            == sorted(rim_pattern + body.board_screw_points()),
            "top and support plates share the rim's %d screws plus %d on the holder",
            len(rim_pattern), len(body.board_screw_points()),
        )
        check(
            body.insert_depth * 2 < body.depth,
            "top and bottom inserts (%.0fmm each) do not meet in the %.0fmm boss",
            body.insert_depth, body.depth,
        )
        check(
            body.insert_depth < body.board_holder_thickness,
            "holder inserts (%.0fmm) stop inside the %.0fmm slab",
            body.insert_depth, body.board_holder_thickness,
        )
        return results

    def check(self) -> list[tuple[bool, str]]:
        """Run :meth:`checks`, raising ``ValueError`` on the first failure."""
        results = self.checks()
        failed = [text for ok, text in results if not ok]
        if failed:
            raise ValueError("fit check failed: " + "; ".join(failed))
        return results

    def height(self) -> float:
        """Overall height of the stack."""
        return sum(part.depth for part in self.parts)

    def fasteners(self) -> list[tuple[int, str]]:
        """What it takes to bolt together, as ``(count, description)``.

        Nothing here threads into plastic directly: the printed body takes
        brass heat-set inserts, and every screw is an M3 machine screw into
        one of those.  The two exceptions are the board itself, which
        self-taps into its standoffs, and the dowels, which are plain rod.
        """
        top = self.part(SanwaTopPlate)
        support = self.part(SanwaSupportPlate)
        bottom = self.part(SanwaBottomPlate)
        body = self.part(SanwaBody)

        # A screw wants to reach most of the way down the insert without
        # bottoming out in it.
        def length(through: float) -> float:
            standard = (6, 8, 10, 12, 14, 16, 20, 25)
            wanted = through + body.insert_depth - 1.5
            return next((s for s in standard if s >= wanted), math.ceil(wanted))

        rim = len(body.mounting_points())
        holder = len(body.board_screw_points())
        low = len(bottom.mounting_points())
        posts = len(body.board_hole_points())

        return [
            (rim + holder + low, f"M3 heat-set inserts, {body.insert_diameter}mm hole "
                                f"x {body.insert_depth:.0f}mm deep"),
            (rim + holder, f"M3 x {length(top.depth + support.depth):.0f} screws, "
                           f"down through both top plates into the body"),
            (low, f"M3 x {length(bottom.depth):.0f} screws, up through the bottom plate"),
            (posts, f"M3 x 8 self-tapping screws, up into the board standoffs"),
            (2, f"{body.join_pin_diameter:.0f}mm dowels x "
                f"{body.join_pin_depth * 2:.0f}mm, locating the printed halves"),
        ]


def _free_spans(blocked, low, high) -> list[tuple[float, float]]:
    """What is left of ``(low, high)`` once overlapping ``blocked`` spans are
    merged and taken out of it."""
    merged: list[list[float]] = []
    for start, end in sorted(blocked):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    free = []
    edge = low
    for start, end in merged:
        if start > edge:
            free.append((edge, min(start, high)))
        edge = max(edge, end)
        if edge >= high:
            break
    if edge < high:
        free.append((edge, high))
    return [(a, b) for a, b in free if b > a]


def _min_bezel_gap(buttons, bezel_clearance) -> float:
    gap = math.inf
    for i, (x0, y0, d0) in enumerate(buttons):
        for x1, y1, d1 in buttons[i + 1:]:
            reach = (d0 + d1 + 2 * bezel_clearance) / 2
            gap = min(gap, math.hypot(x1 - x0, y1 - y0) - reach)
    return gap


def _min_edge_gap(buttons, bezel_clearance, width, height) -> float:
    gap = math.inf
    for x, y, d in buttons:
        radius = (d + bezel_clearance) / 2
        gap = min(gap, width / 2 - abs(x) - radius, height / 2 - abs(y) - radius)
    return gap


def _min_screw_gap(buttons, bezel_clearance, plate, boss_radius) -> float:
    gap = math.inf
    for sx, sy in plate.mounting_points():
        for x, y, d in buttons:
            reach = (d + bezel_clearance) / 2 + boss_radius
            gap = min(gap, math.hypot(sx - x, sy - y) - reach)
    return gap


def _outline_gap(plate: "SanwaPlate", point: tuple[float, float], inset: float = 0.0) -> float:
    """Signed distance from a point to the outline, positive inside.

    The outline is convex, so the perpendicular distance to the nearest edge
    line is the real clearance.  ``inset`` measures against the outline pulled
    in by that much -- the cavity wall, say.  Negative means the point has
    fallen off the edge, which is exactly what a chamfered corner does to a
    screw that was placed as if the corner were square.
    """
    points = plate.profile_points(inset)
    gap = math.inf
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        side = ((point[0] - x0) * dy - (point[1] - y0) * dx) / length
        # The origin is inside, so its sign is the one that means "inside".
        reference = (-x0 * dy + y0 * dx) / length
        gap = min(gap, side if reference > 0 else -side)
    return gap


def _min_rear_gap(body: "SanwaBody") -> float:
    """Clearance between the rear components themselves."""
    spans = body.rear_spans()
    gap = math.inf
    for (_, end), (start, _) in zip(spans, spans[1:]):
        gap = min(gap, start - end)
    return gap


def _min_rear_boss_gap(body: "SanwaBody") -> float:
    """Clearance between the rear components and the screw bosses.

    The bosses stand in the same wall the rear components mount in, and a
    button's body reaches 24.5mm back past them, so this is the clearance that
    decides whether the back panel can be laid out at all.
    """
    boss = body.boss_diameter / 2
    gap = math.inf
    for start, end in body.rear_spans():
        for x in body.rear_boss_points():
            gap = min(gap, max(start - (x + boss), (x - boss) - end))
    return gap


def _widest_rear_span(body: "SanwaBody") -> float:
    """The longest stretch of back edge with no screw holding it down.

    Measured from one end of the straight edge to the other, so a wall too
    crowded to take any screw at all reports its whole length rather than
    having nothing to compare.
    """
    limit = body.straight_half("x", body.screw_inset)
    edges = [-limit] + sorted(body.rear_screw_points()) + [limit]
    return max(b - a for a, b in zip(edges, edges[1:]))


def _rear_bodies(body: "SanwaBody") -> list[tuple[float, float, float, float]]:
    """What each rear component occupies inside the case.

    ``(x0, x1, reach, height)`` -- the span along the wall, how far the body
    reaches into the cavity, and how tall it is on the wall.
    """
    bodies = []
    half = body.rear_button.hole_diameter / 2
    for x in body.rear_button_points():
        bodies.append((x - half, x + half, body.rear_button.below_panel,
                       body.rear_button.hole_diameter))
    jack = body.usb_jack
    bodies.append((body.usb_offset - jack.bore / 2, body.usb_offset + jack.bore / 2,
                   jack.depth_behind_panel, jack.bore))
    return bodies


def _min_rear_face_gap(body: "SanwaBody", buttons, bezel_clearance, face_reach) -> float:
    """Plan clearance between the rear component bodies and the face buttons.

    Both hang inside the same cavity: the face buttons down from the top plate,
    the rear ones back from the wall.  Where they overlap in height, they have
    to miss each other in plan.  The face button envelope is taken as its bezel
    diameter, which is a little conservative -- the body behind the panel is
    slightly narrower than the bezel in front of it.
    """
    inner = body.height / 2 - body.wall_thickness
    face_bottom = body.depth - face_reach
    gap = math.inf
    for x0, x1, reach, height in _rear_bodies(body):
        if body.depth / 2 + height / 2 <= face_bottom:
            continue  # passes below anything hanging from the top plate
        gap = min(gap, _min_rect_button_gap(
            buttons, bezel_clearance, (x0, inner - reach, x1, inner)))
    return gap


def _board_extent(body: "SanwaBody") -> tuple[float, float, float, float]:
    """The board's own footprint, ``(x0, y0, x1, y1)`` -- the holder around it
    is larger, and reaches back to a wall."""
    cx, cy = body.board_center
    bw, bh = body.board_size
    return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)


def _min_rear_holder_gap(body: "SanwaBody") -> float:
    """Plan clearance between the rear component bodies and the board holder.

    The holder is a slab under the lid and the rear components reach back at
    much the same height, so if they overlap in plan they overlap for real.
    """
    inner = body.height / 2 - body.wall_thickness
    holder_top = body.depth - body.board_holder_thickness
    x0, y0, x1, y1 = body.board_holder_extent()
    gap = math.inf
    for bx0, bx1, reach, height in _rear_bodies(body):
        if body.depth / 2 + height / 2 <= holder_top:
            continue  # passes below the slab
        dx = max(x0 - bx1, 0.0, bx0 - x1)
        dy = max((inner - reach) - y1, 0.0, y0 - inner)
        gap = min(gap, math.hypot(dx, dy) if (dx or dy) else -min(
            bx1 - x0, x1 - bx0, y1 - (inner - reach), inner - y0))
    return gap


def _min_rect_button_gap(buttons, bezel_clearance, rect) -> float:
    """Plan clearance between a rectangle and every button bezel."""
    x0, y0, x1, y1 = rect
    gap = math.inf
    for x, y, d in buttons:
        dx = max(x0 - x, 0.0, x - x1)
        dy = max(y0 - y, 0.0, y - y1)
        gap = min(gap, math.hypot(dx, dy) - (d + bezel_clearance) / 2)
    return gap


def _min_split_gap(body: "SanwaBody") -> float:
    """How much clear wall the split has either side of it."""
    gap = math.inf
    split = body.split_x()
    for start, end in body.rear_spans():
        gap = min(gap, max(start - split, split - end))
    return gap


def _half_sizes(body: "SanwaBody") -> list[tuple[float, float]]:
    """Footprint of each printed half."""
    left = body.split_x() + body.width / 2
    return [(left, body.height), (body.width - left, body.height)]


#: The four-part Sanwa stack, in the order it is bolted together.
sanwaFgc = SanwaAssembly(
    parts=(
        SanwaBottomPlate(),
        SanwaBody(),
        SanwaSupportPlate(),
        SanwaTopPlate(),
    )
)

#: The same stack on the :class:`~makoreactor.layouts.FgcPlus` layout.
#:
#: Hands 200mm apart, four buttons under the left one and two thumb buttons
#: under each, makes for a bigger plate: 460 x 215mm against 320 x 200.  The
#: board goes under the right palm, outboard of the thumb cluster, with a
#: short neck forward to the wall.  That corner is what sets the width: with
#: the thumbs where the smash layouts put MX and MY they take the inboard half
#: of it, and the layout is centred, so the room has to come from both sides.
#: Its two printed halves want a 250mm bed rather than a 220mm one.
sanwaFgcPlus = sanwaFgc.set(
    layout=FgcPlus(),
    width=460.0,
    height=215.0,
    board_center=(154.0, -48.0),
    print_bed=(250.0, 250.0),
)
