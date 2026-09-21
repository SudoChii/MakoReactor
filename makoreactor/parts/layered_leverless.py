"""Parametric parts for a layered leverless controller.

The controller is a stack of flat plates bolted together at the corners, so
every part here is a prism that can be exported to DXF and cut on a laser or
router::

    Backplate         cosmetic top, button holes
    F1CapFaceplate    button holes sized for the caps
    Switchplate       square switch mounts
    WireSpaceModelU   spacer that makes room for wiring and the USB-C port
    Base              solid bottom

Dimensions were recovered from the reference exports checked in under
``notebooks/mako1_fgc/`` and ``notebooks/artifacts/mako1/``; ``tests/`` asserts
that the generated geometry still reproduces them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace
from typing import Sequence

import cadquery as cq

from makoreactor.layouts import CircleCapLeverless, Layout, SquareCapLeverless, WideGc


def in2mm(value: float) -> float:
    """Inches to millimetres."""
    return value * 25.4


def _replace_part(part: "PlatePart", **kwargs) -> "PlatePart":
    """Apply the subset of ``kwargs`` that ``part`` actually accepts."""
    valid = {f.name for f in fields(part)}
    return replace(part, **{k: v for k, v in kwargs.items() if k in valid})


def _corners(width: float, height: float) -> list[tuple[float, float]]:
    return [(x, y) for x in (-width / 2, width / 2) for y in (-height / 2, height / 2)]


#: Cycled over the layers by :meth:`LayeredAssembly.assemble` so a stacked
#: render is readable.  Roughly the look of a smoked-acrylic build.
LAYER_COLORS = ("gray", "steelblue", "darkslategray", "lightsteelblue", "gray")


@dataclass(frozen=True)
class BrookBoard:
    """A Brook fight board, as far as the case around it has to care.

    ``size`` is the PCB outline and ``hole_pitch`` the centre-to-centre
    rectangle its four mounting holes sit on -- measured off the board, not
    derived from an inset, because the two axes do not inset equally.  The
    heights are what the stack has to find room for, with the board hanging
    face-up under the faceplate::

        component_height    tallest thing on top of the PCB
        thickness           the PCB itself
        below_board         solder tails and pin ends under it

    ``component_height`` is still an assumption -- Brook publishes no height --
    and it is the number that decides whether the faceplate closes over the
    board.  Measure it before cutting.
    """

    size: tuple[float, float] = (96.0, 45.0)
    #: Centre-to-centre spacing of the four mounting holes, measured.
    hole_pitch: tuple[float, float] = (87.71, 36.96)
    #: The holes themselves, and the M3 hardware that goes through them.
    screw_diameter: float = 3.3
    screw_head_diameter: float = 6.0
    screw_head_height: float = 2.0
    thickness: float = 1.6
    #: Tallest component above the PCB.  Assumed; measure this one first.
    component_height: float = 11.0
    #: Left clear underneath for solder tails and the ends of the headers.
    below_board: float = 3.0

    def hole_offsets(self) -> list[tuple[float, float]]:
        """The four mounting holes, relative to the centre of the board."""
        dx, dy = self.hole_pitch[0] / 2, self.hole_pitch[1] / 2
        return [(sx * dx, sy * dy) for sx in (-1, 1) for sy in (-1, 1)]

    def hole_insets(self) -> tuple[float, float]:
        """How far the holes sit in from the board edge, per axis."""
        return ((self.size[0] - self.hole_pitch[0]) / 2,
                (self.size[1] - self.hole_pitch[1]) / 2)

    def seated_depth(self) -> float:
        """What the board needs below its own top face: the PCB and its tails.

        The board hangs as low as its standoffs allow, so this is the part of
        the wire space it takes up; everything above it is standoff, and the
        components live in that gap.
        """
        return self.thickness + self.below_board


@dataclass
class Base(PlatePart):
    """Solid bottom plate: outline and mounting holes only."""

    def generate(self) -> cq.Workplane:
        return self._cut_mounting_holes(self.blank())


@dataclass
class WireSpaceModelU(PlatePart):
    """Spacer that opens up the interior for wiring and the USB-C port.

    Everything is cut through, so the layer is a frame: an outer wall of
    ``wall_thickness``, square pads at the corners carrying the mounting holes,
    and a boss at the top edge holding the USB-C breakout.

    Going inwards from the plate edge, the USB-C opening is:

    * ``usbc_slot_width`` — the connector pokes out through the wall here.
    * a pocket ``usbc_pocket_width`` x ``usbc_pocket_depth``, starting
      ``usbc_pocket_inset`` in from the edge.  The little breakout PCB carrying
      the receptacle sits in this pocket.
    * two ``usbc_relief_radius`` semicircles, tangent to the pocket walls and
      centred on its top edge, so the board can be seated and levered back out.
    * ``usbc_throat_width`` — the wire throat down into the cavity, between the
      two arms of the boss.
    """

    depth: float = 6.35  # 1/4"
    wall_thickness: float = 10
    support_inset: float = 22.5
    cavity_fillet: float = 2

    usbc_offset: float = 0
    usbc_boss_width: float = 40
    usbc_pocket_width: float = 20.5
    usbc_pocket_depth: float = 9.0
    usbc_pocket_inset: float = 6.25
    usbc_relief_radius: float = 5.0
    usbc_throat_width: float = 13
    usbc_slot_width: float = 13
    usbc_fillet: float = 3

    def part_depth(self) -> float:
        """Wire space scales with the number of ModelU boards being housed."""
        return self.depth * max(self.n_modelu, 1)

    def _cavity(self, depth: float) -> cq.Workplane:
        """The material to remove: interior frame minus supports and USB boss."""
        top = self.height / 2

        def prism(width, height, center):
            return cq.Workplane("XY").center(*center).rect(width, height).extrude(depth)

        # Interior frame, less square pads at each plate corner so the mounting
        # holes keep material around them.
        ring = prism(
            self.width - self.wall_thickness * 2,
            self.height - self.wall_thickness * 2,
            (0, 0),
        )
        pads = (
            cq.Workplane("XY")
            .pushPoints(_corners(self.width - self.support_inset, self.height - self.support_inset))
            .rect(self.support_inset, self.support_inset)
            .extrude(depth)
        )
        ring = self._fillet_vertical(ring.cut(pads), self.cavity_fillet)

        # Boss at the top edge carrying the USB-C receptacle, split in two by
        # the cable throat.  Only the stretch reaching into the cavity is
        # modelled — past that it merges into the outer wall — and it is
        # filleted before being subtracted so the arms keep their own radius
        # rather than the cavity's.  Just the corners facing into the cavity
        # are rounded; the far ends run into the wall.
        arm_height = self.support_inset - self.wall_thickness
        arm_center = (self.usbc_offset, top - self.wall_thickness - arm_height / 2)
        throat = prism(self.usbc_throat_width, arm_height, arm_center)
        arms = prism(self.usbc_boss_width, arm_height, arm_center).cut(throat)
        ring = ring.cut(self._fillet_vertical(arms, self.usbc_fillet, "<Y"))

        # Seat for the USB-C breakout board, with a semicircular relief either
        # side of it so the board can be lifted back out.  The reliefs are
        # tangent to the pocket walls, so only their top halves show.
        pocket_top = top - self.usbc_pocket_inset
        pocket = prism(
            self.usbc_pocket_width,
            self.usbc_pocket_depth,
            (self.usbc_offset, pocket_top - self.usbc_pocket_depth / 2),
        )
        relief_offset = self.usbc_pocket_width / 2 - self.usbc_relief_radius
        reliefs = (
            cq.Workplane("XY")
            .pushPoints([
                (self.usbc_offset - relief_offset, pocket_top),
                (self.usbc_offset + relief_offset, pocket_top),
            ])
            .circle(self.usbc_relief_radius)
            .extrude(depth)
        )

        # The connector itself pokes out through the outer wall.
        slot = prism(
            self.usbc_slot_width,
            self.usbc_pocket_inset * 2,
            (self.usbc_offset, pocket_top + self.usbc_pocket_inset),
        )

        opening = pocket.union(reliefs).union(slot)

        # Round the mouth where the slot breaks the wall.  This rounds material,
        # but the wall left above the pocket is thinner than the radius, so OCC
        # will not fillet it — the flare is cut instead, as a corner square with
        # a disk taken out of it.
        radius = self.usbc_fillet
        if radius > 0:
            half = self.usbc_slot_width / 2
            corners = [
                (self.usbc_offset - half - radius, top - radius),
                (self.usbc_offset + half + radius, top - radius),
            ]
            squares = (
                cq.Workplane("XY")
                .pushPoints([(x + radius / 2 * (1 if x < self.usbc_offset else -1),
                              y + radius / 2) for x, y in corners])
                .rect(radius, radius)
                .extrude(depth)
            )
            disks = (
                cq.Workplane("XY").pushPoints(corners).circle(radius).extrude(depth)
            )
            opening = opening.union(squares.cut(disks))

        return ring.union(opening).translate((0, 0, -depth / 2))

    @staticmethod
    def _fillet_corners(solid: cq.Workplane, radius: float, points, tol: float = 0.25):
        """Round the vertical edges standing at the given ``(x, y)`` corners.

        Used for the two blends that cannot be built into the cutters, because
        they round material rather than void: where the boss arms meet the
        outer wall, and where the connector slot breaks through it.
        """
        if radius <= 0 or not points:
            return solid

        try:
            wanted = []
            for edge in solid.edges("|Z").vals():
                center = edge.Center()
                if any(abs(center.x - px) < tol and abs(center.y - py) < tol
                       for px, py in points):
                    wanted.append(edge)
            if not wanted:
                return solid
            return solid.newObject(wanted).fillet(radius)
        except Exception:
            return solid

    @staticmethod
    def _fillet_vertical(solid: cq.Workplane, radius: float, where: str = None) -> cq.Workplane:
        """Round vertical edges, optionally narrowed by a further selector."""
        if radius <= 0:
            return solid
        try:
            edges = solid.edges("|Z")
            if where:
                edges = edges.edges(where)
            return edges.fillet(radius)
        except Exception:
            # Geometry too tight for this radius; leave the corners sharp
            # rather than failing the whole part.
            return solid

    def generate(self) -> cq.Workplane:
        # Cut at whatever depth the layer actually works out to.  For this
        # class that is ``n_modelu`` thicknesses of stock; a subclass can have
        # its own reason to be deeper, so the test is on the depth itself.
        deeper = self.part_depth() != self.depth
        part = replace(self, depth=self.part_depth()) if deeper else self
        plate = part._cut_mounting_holes(part.blank())
        plate = plate.cut(part._cavity(part.depth * 3))

        # Blend the boss arms into the outer wall.  This one adds material at a
        # reentrant corner, so it cannot be built into the cutter.
        top = part.height / 2
        return part._fillet_corners(
            plate,
            part.usbc_fillet,
            [
                (part.usbc_offset - part.usbc_boss_width / 2, top - part.wall_thickness),
                (part.usbc_offset + part.usbc_boss_width / 2, top - part.wall_thickness),
            ],
        )




@dataclass
class KeycapFaceplate(PlatePart):
    """Faceplate cut for square MX keycaps."""

    layout: Layout = field(default_factory=SquareCapLeverless)

    def generate(self) -> cq.Workplane:
        return self._cut_layout(self._cut_mounting_holes(self.blank()))


@dataclass
class Backplate(PlatePart):
    """Cosmetic top plate; shares the faceplate's button openings."""

    def generate(self) -> cq.Workplane:
        return self._cut_layout(self._cut_mounting_holes(self.blank()))


@dataclass
class BrookWireSpace(WireSpaceModelU):
    """The wire space, deep enough to hang a Brook board in.

    The layer is already an open frame, so a board in the middle of it needs no
    new cutout -- what it needs is depth.  The plates are cut from sheet, so
    depth only comes in whole thicknesses of stock: :meth:`spacers` works out
    how many 1/4" layers the board takes and :meth:`part_depth` never returns
    less, whatever ``n_modelu`` says.

    :attr:`board_margin` is the room kept round the PCB, and it is not square:
    the wires leave from the ends of the long axis, so that is where the space
    goes.
    """

    board: BrookBoard = field(default_factory=BrookBoard)
    #: Centre of the board on the plate.  The default sits it below the button
    #: field and between the two thumb clusters.
    board_center: tuple[float, float] = (0.0, -22.0)
    #: Room kept round the PCB as ``(x, y)``: 10mm at each end of the long axis
    #: for the wires to leave from, and enough on the long edges to cut to.
    board_margin: tuple[float, float] = (10.0, 3.0)

    def spacers(self) -> int:
        """1/4" layers this spacer is made of: enough for the board, at least."""
        needed = math.ceil(self.board.seated_depth() / self.depth)
        return max(self.n_modelu, needed, 1)

    def part_depth(self) -> float:
        return self.depth * self.spacers()

    def board_extent(self) -> tuple[float, float, float, float]:
        """The PCB itself on the plate, ``(x0, y0, x1, y1)``."""
        cx, cy = self.board_center
        dx, dy = self.board.size[0] / 2, self.board.size[1] / 2
        return (cx - dx, cy - dy, cx + dx, cy + dy)

    def wire_extent(self) -> tuple[float, float, float, float]:
        """The board plus the room its wires want, ``(x0, y0, x1, y1)``."""
        x0, y0, x1, y1 = self.board_extent()
        mx, my = self.board_margin
        return (x0 - mx, y0 - my, x1 + mx, y1 + my)

    def board_hole_points(self) -> list[tuple[float, float]]:
        """The four mounting holes in plate coordinates."""
        cx, cy = self.board_center
        return [(cx + dx, cy + dy) for dx, dy in self.board.hole_offsets()]


@dataclass
class BrookSwitchplate(Switchplate):
    """The switchplate, opened up to let the board and its standoffs through.

    The board does not hang from this plate -- it hangs from the faceplate
    above it, see :class:`BrookFaceplate` -- so what this one needs is to get
    out of the way of two things:

    * the four standoffs, which pass straight through it on their way down to
      the board.  :attr:`standoff_clearance` is a hole per standoff, sized for
      the body rather than the screw.
    * the components on top of the board, which reach up into this plate's
      thickness.  The window is set out from the *hole pattern* rather than the
      board edge, so :attr:`board_rim` is exactly the material left between the
      window and each standoff hole.

    Everything goes all the way through, because these plates are cut flat --
    there is no such thing as a pocket here.
    """

    board: BrookBoard = field(default_factory=BrookBoard)
    board_center: tuple[float, float] = (0.0, -22.0)
    #: Clearance hole for the body of an M3 standoff, not the screw: a hex one
    #: measures ~5.5mm across the corners.
    standoff_clearance: float = 6.5
    #: Material left between the relief window and each standoff hole.
    board_rim: float = 3.0
    #: Rounded so the window has no sharp internal corner to start a crack.
    board_relief_fillet: float = 3.0
    #: Off leaves just the four standoff holes, for a stack deep enough to keep
    #: the components clear of this plate entirely.
    board_relief: bool = True

    def board_hole_points(self) -> list[tuple[float, float]]:
        """The four standoff holes in plate coordinates."""
        cx, cy = self.board_center
        return [(cx + dx, cy + dy) for dx, dy in self.board.hole_offsets()]

    def relief_size(self) -> tuple[float, float]:
        """The window over the board, ``(width, height)``.

        The hole pattern pulled in by half a standoff hole and the rim, so the
        window stops :attr:`board_rim` short of each standoff.
        """
        edge = self.standoff_clearance + 2 * self.board_rim
        return (self.board.hole_pitch[0] - edge, self.board.hole_pitch[1] - edge)

    def rim_to_hole(self) -> float:
        """Material between the window edge and the nearest standoff hole."""
        return self.board_rim

    def _board_relief(self) -> cq.Workplane:
        width, height = self.relief_size()
        window = (
            self._cutter()
            .center(*self.board_center)
            .rect(width, height)
            .extrude(self.depth * 3)
        )
        radius = self.board_relief_fillet
        if 0 < radius < min(width, height) / 2:
            try:
                window = window.edges("|Z").fillet(radius)
            except Exception:
                pass
        return window

    def generate(self) -> cq.Workplane:
        plate = super().generate()

        standoffs = (
            self._cutter()
            .pushPoints(self.board_hole_points())
            .circle(self.standoff_clearance / 2)
            .extrude(self.depth * 3)
        )
        plate = plate.cut(standoffs)

        if self.board_relief:
            plate = plate.cut(self._board_relief())
        return plate


@dataclass
class BrookFaceplate(F1CapFaceplate):
    """The faceplate, drilled for the four screws the board hangs from.

    Of the two plates the buttons pass through this is the upper one, and it is
    the only plate in the stack thick enough and solid enough to carry the
    board: the switchplate below it is mostly holes where the board wants to
    be.  So the standoffs land here, and the screws drop through from above.
    """

    board: BrookBoard = field(default_factory=BrookBoard)
    board_center: tuple[float, float] = (0.0, -22.0)

    def board_hole_points(self) -> list[tuple[float, float]]:
        """The four screw holes in plate coordinates."""
        cx, cy = self.board_center
        return [(cx + dx, cy + dy) for dx, dy in self.board.hole_offsets()]

    def generate(self) -> cq.Workplane:
        plate = super().generate()
        screws = (
            self._cutter()
            .pushPoints(self.board_hole_points())
            .circle(self.board.screw_diameter / 2)
            .extrude(self.depth * 3)
        )
        return plate.cut(screws)


@dataclass
class BrookBackplate(Backplate):
    """The cosmetic top, relieved so the board's screw heads have somewhere to go.

    The screws that hold the board go down through the faceplate, which leaves
    four heads standing proud of it -- and this plate lies straight on top.
    Without a clearance hole each one they would hold the two plates apart.
    The heads are shorter than this plate is thick, so they disappear into it.
    """

    board: BrookBoard = field(default_factory=BrookBoard)
    board_center: tuple[float, float] = (0.0, -22.0)

    def board_hole_points(self) -> list[tuple[float, float]]:
        cx, cy = self.board_center
        return [(cx + dx, cy + dy) for dx, dy in self.board.hole_offsets()]

    def generate(self) -> cq.Workplane:
        plate = super().generate()
        heads = (
            self._cutter()
            .pushPoints(self.board_hole_points())
            .circle(self.board.screw_head_diameter / 2)
            .extrude(self.depth * 3)
        )
        return plate.cut(heads)


@dataclass
class LayeredAssembly:
    """An ordered stack of plates sharing a common set of parameters."""

    parts: Sequence[PlatePart]

    def set(self, **kwargs) -> "LayeredAssembly":
        """Return a copy with ``kwargs`` applied to every part that accepts them."""
        return replace(self, parts=tuple(_replace_part(part, **kwargs) for part in self.parts))

    def part(self, kind):
        """The first part in the stack that is an instance of ``kind``."""
        for part in self.parts:
            if isinstance(part, kind):
                return part
        raise LookupError(f"no {kind.__name__} in this assembly")

    def generate(self) -> list[cq.Workplane]:
        """Generate every part, in stack order."""
        return [part.generate() for part in self.parts]

    def assemble(self, gap: float = 0.0, colors: Sequence[str] = None) -> cq.Assembly:
        """Generate every part and stack it along +Z for viewing.

        ``gap`` inserts space between the layers, which makes an exploded view
        that is much easier to read in a 3-D viewer.  ``colors`` is cycled over
        the layers so they can be told apart.
        """
        palette = list(colors) if colors else list(LAYER_COLORS)

        assembly = cq.Assembly()
        z = 0.0
        for index, part in enumerate(self.parts):
            depth = part.part_depth() if isinstance(part, WireSpaceModelU) else part.depth
            assembly.add(
                part.generate(),
                name=type(part).__name__,
                loc=cq.Location(cq.Vector(0, 0, z)),
                color=cq.Color(palette[index % len(palette)]),
            )
            z += depth + gap
        return assembly

    def __len__(self) -> int:
        return len(self.parts)

    def __iter__(self):
        return iter(self.parts)


def _rect(center: tuple[float, float], size: tuple[float, float]):
    """An axis-aligned ``(x0, y0, x1, y1)`` from a centre and a size."""
    (cx, cy), (width, height) = center, size
    return (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


def _rect_gap(a, b) -> float:
    """Separation between two axis-aligned rects, negative if they overlap."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1)
    dy = max(by0 - ay1, ay0 - by1)
    if dx >= 0 and dy >= 0:
        return math.hypot(dx, dy)
    return max(dx, dy)


def _inside_gap(inner, outer) -> float:
    """How far ``inner`` is from the nearest wall of ``outer``; negative if out."""
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    return min(ix0 - ox0, iy0 - oy0, ox1 - ix1, oy1 - iy1)


@dataclass
class BrookAssembly(LayeredAssembly):
    """A layered stack with a Brook board hung under the switchplate.

    The board goes in the wire space, face up, on standoffs screwed down
    through the switchplate.  Everything that follows from that is checked
    rather than assumed, because the numbers pull against each other: a deeper
    wire space means longer standoffs and a shallower window, a bigger board
    means less room between the thumb clusters, and the switchplate can only
    swallow components as tall as it is thick before the faceplate is in the
    way.  :meth:`checks` states each of those as a measurement.

    Build order is the one the geometry implies: standoffs onto the board,
    board up into the wire space, switchplate down on top and four screws
    through it, then the faceplate closes the window over the components.
    """

    def height(self) -> float:
        """Overall height of the stack."""
        return sum(
            part.part_depth() if isinstance(part, WireSpaceModelU) else part.depth
            for part in self.parts
        )

    def checks(self) -> list[tuple[bool, str]]:
        """Every fit constraint the board imposes, as ``(ok, description)``."""
        space = self.part(BrookWireSpace)
        switch = self.part(BrookSwitchplate)
        board = space.board
        results: list[tuple[bool, str]] = []

        def check(ok, fmt, *args):
            results.append((bool(ok), fmt % args))

        # The wire space has to hold the board itself; the standoffs are
        # whatever depth is left once what hangs under the PCB has cleared.
        check(
            space.standoff_length() > 0,
            "wire space %.2fmm (%d x %.2fmm stock) hangs the board on "
            "%.2fmm standoffs",
            space.part_depth(), space.spacers(), space.depth, space.standoff_length(),
        )

        # Components taller than the standoffs go up through the switchplate.
        # Taller than the switchplate as well and they hit the faceplate.
        relief = space.relief_depth()
        if relief > 0:
            check(
                relief <= switch.depth,
                "components stand %.2fmm proud of the switchplate's underside, "
                "within its %.2fmm thickness (%d spacers would clear it entirely)",
                relief, switch.depth, space.spacers_without_relief(),
            )
            check(
                switch.board_relief,
                "the switchplate is opened up over the board, which needs "
                "%.2fmm of relief",
                relief,
            )
        else:
            check(True, "board clears the switchplate by %.2fmm; no window needed",
                  -relief)

        # The window must not eat the screws that hold the board up.
        check(
            switch.rim_to_hole() > 0,
            "window leaves %.2fmm of material between its edge and each screw",
            switch.rim_to_hole(),
        )
        check(
            space.board_center == switch.board_center and space.board == switch.board,
            "wire space and switchplate agree on the board and where it sits",
        )

        # On the plate: the board must clear the buttons, the switch mounts and
        # the corner screws, and sit inside the cavity wall.
        extent = space.board_extent()
        layout = list(switch.layout)
        if layout:
            mount = min(
                _rect_gap(extent, _rect(point, switch.switch_mount_dims))
                for point in layout
            )
            check(mount > 0, "board clears the nearest switch mount by %.1fmm", mount)

        corner = min(
            _rect_gap(extent, _rect(point, (space.hole_diameter,) * 2))
            for point in space.mounting_points()
        )
        check(corner > 0, "board clears the nearest corner screw by %.1fmm", corner)

        cavity = _rect(
            (0, 0),
            (space.width - 2 * space.wall_thickness, space.height - 2 * space.wall_thickness),
        )
        wall = _inside_gap(extent, cavity)
        check(wall > 0, "board sits %.1fmm inside the cavity wall", wall)

        pad = min(
            _rect_gap(extent, _rect(point, (space.support_inset,) * 2))
            for point in _corners(
                space.width - space.support_inset, space.height - space.support_inset
            )
        )
        check(pad > 0, "board clears the nearest corner pad by %.1fmm", pad)

        # The four screws have to land on material, not in a switch mount.
        screw = (switch.board.screw_diameter,) * 2
        if layout:
            near = min(
                _rect_gap(_rect(hole, screw), _rect(point, switch.switch_mount_dims))
                for hole in switch.board_hole_points()
                for point in layout
            )
            check(near > 0, "every board screw clears a switch mount, "
                            "the tightest by %.1fmm", near)

        return results

    def check(self) -> list[tuple[bool, str]]:
        """Run :meth:`checks`, raising ``ValueError`` on the first failure."""
        results = self.checks()
        failed = [text for ok, text in results if not ok]
        if failed:
            raise ValueError("fit check failed: " + "; ".join(failed))
        return results

def _assembly(*parts: PlatePart) -> LayeredAssembly:
    return LayeredAssembly(parts=parts)


#: Five-layer stack with a Frame 1 cap faceplate.
f1CapMako1 = _assembly(
    Base(),
    WireSpaceModelU(),
    Switchplate(),
    F1CapFaceplate(),
    Backplate(),
)

#: Five-layer stack with an MX keycap faceplate.
mako1 = _assembly(
    Base(),
    WireSpaceModelU(),
    Switchplate(),
    KeycapFaceplate(),
    Backplate(),
)


#: Five-layer stack with room for a Brook board under the switchplate.
#:
#: Two layers differ from :data:`f1CapMako1`: the wire space is deep enough to
#: hang the board in, and the switchplate is drilled for its four screws and
#: opened up over its components.  Two 1/4" spacers, which is what makes the
#: window shallow enough for the switchplate to swallow on its own.
brookMako1 = BrookAssembly(
    parts=(
        Base(),
        BrookWireSpace(),
        BrookSwitchplate(),
        F1CapFaceplate(),
        Backplate(),
    )
).set(layout=WideGc(), n_modelu=2)
