"""Button layouts for leverless ("hitbox" style) fight controllers.

A :class:`Layout` owns button centre points grouped by hand/function, plus a 2-D
affine that places each group on the plate.  ``layout`` flattens the groups into
plate coordinates; ``geom`` returns the same points as CadQuery geometry, ready
to be cut out of a faceplate.

Coordinates are millimetres, origin at the centre of the plate, +X right and
+Y towards the far edge.
"""

import copy

import cadquery as cq
import numpy as np
from affine import Affine

# Group names in the order they are concatenated by ``Layout.layout``.
GROUPS = ("left_homerow", "right_homerow", "left_thumb", "right_thumb", "misc")


class Layout:
    """Base class for button layouts.

    Subclasses declare, for each name in :data:`GROUPS`, a ``<group>_coords``
    sequence of ``(x, y)`` points and a ``<group>_affine`` placing that group on
    the plate.  An empty ``_coords`` disables the group.
    """

    #: Applied on top of the per-group affines, e.g. to nudge the whole cluster.
    layout_affine = Affine.identity()

    @property
    def geom(self):
        raise NotImplementedError("Layout subclasses must implement 'geom'")

    @property
    def layout(self):
        raise NotImplementedError("Layout subclasses must implement 'layout'")

    def placed(self, group):
        """Return ``<group>_coords`` mapped through ``<group>_affine``."""
        if group not in GROUPS:
            raise ValueError(f"unknown layout group {group!r}, expected one of {GROUPS}")

        coords = getattr(self, f"{group}_coords")
        if len(coords) == 0:
            return []

        coords = np.asarray(coords, dtype=float)
        if coords.ndim != 2 or coords.shape[1] != 2:
            raise ValueError(
                f"{group}_coords must be a sequence of (x, y) pairs, got shape {coords.shape}"
            )

        affine = getattr(self, f"{group}_affine")
        return [tuple(affine * tuple(point)) for point in coords]

    def tolist(self):
        return list(self.layout)

    def __mul__(self, val: Affine):
        """Return a copy with ``val`` applied after the existing layout affine."""
        placed = copy.copy(self)
        placed.layout_affine = self.layout_affine * val
        return placed

    def __rmul__(self, val: Affine):
        """Return a copy with ``val`` applied before the existing layout affine."""
        placed = copy.copy(self)
        placed.layout_affine = val * self.layout_affine
        return placed

    def __iter__(self):
        return iter(self.layout)

    def __len__(self):
        return len(self.layout)

    def __repr__(self):
        return f"{type(self).__name__}({len(self)} buttons)"


class CircleCapLeverless(Layout):
    """Leverless layout for circular Frame 1 caps.

    Similar to the GCCMX layout but with a single centre button for start.
    """

    right_homerow_coords = [
        (-26.15, -11.75), (0, 0), (26.65, -3.2), (53.3, -19.45),
        (-26.15, -33.75), (0, -22), (26.65, -25.2), (53.3, -41.45),
    ]

    # The four directional buttons are the last four homerow buttons mirrored in Y.
    left_homerow_coords = np.dot(right_homerow_coords[4:], [[-1, 0], [0, 1]])

    right_thumb_coords = [(0, 0), (-18.5, -12.75), (0, 25.5), (-18.5, 12.75), (18.5, 12.75)]
    # Modifier buttons are the first two c-stick buttons mirrored in Y.
    left_thumb_coords = np.dot(right_thumb_coords[:2], [[-1, 0], [0, 1]])
    misc_coords = [(0, 0)]

    right_homerow_affine = Affine.translation(100, 58)
    left_homerow_affine = Affine.translation(-100, 58)
    left_thumb_affine = Affine.translation(-70, -45)
    right_thumb_affine = Affine.translation(70, -45)
    misc_affine = Affine.translation(0, 18)

    cap_diameter = 22.5
    #: Blends the notch where two overlapping caps meet.  Caps in the thumb
    #: cluster only overlap by hundredths of a millimetre, so the filleted face
    #: there is geometrically degenerate; it still cuts correctly, but do not
    #: rely on ``geom.extrude(...)`` being a valid solid on its own.
    intersection_fillet = 0.5

    @property
    def layout(self):
        points = []
        for group in GROUPS:
            points.extend(self.placed(group))
        return [tuple(self.layout_affine * point) for point in points]

    @property
    def geom(self):
        """Cap outlines as a ``Workplane`` holding one sketch per button group.

        Groups are sketched separately so that ``intersection_fillet`` only
        blends caps that overlap within the same cluster.
        """
        sketches = [self._sketch(self.placed(group)) for group in GROUPS]
        sketches = [s for s in sketches if s is not None]
        if not sketches:
            return cq.Workplane("XY")
        return cq.Workplane("XY").placeSketch(*sketches)

    def _sketch(self, points):
        if not len(points):
            return None

        points = [tuple(self.layout_affine * point) for point in points]
        sketch = (
            cq.Sketch()
            .push(points)
            .circle(self.cap_diameter / 2)  # .circle takes a radius
            .clean()
            .reset()
        )

        try:
            sketch = sketch.vertices().fillet(self.intersection_fillet)
        except Exception:
            # Nothing to fillet: the caps in this group do not intersect.
            pass
        return sketch


class SquareCapLeverless(CircleCapLeverless):
    """Leverless layout for square (MX keycap) buttons."""

    cap_dimensions: tuple[float, float] = (20.5, 20.5)
    cap_fillet_radius: float = 0.1

    def _sketch(self, points):
        if not len(points):
            return None

        points = [tuple(self.layout_affine * point) for point in points]
        sketch = (
            cq.Sketch()
            .push(points)
            .rect(*self.cap_dimensions)
            .clean()
            .reset()
        )

        try:
            sketch = sketch.vertices().fillet(self.cap_fillet_radius)
        except Exception:
            pass
        return sketch


class Gccmx(CircleCapLeverless):
    """A layout mimicking Crane's GCCMX layout.

    Same as :class:`CircleCapLeverless` except for three centre buttons, to
    support things like home and share when combining a Brook with a ModelS.
    """

    misc_coords = [(-20, 0), (0, 0), (20, 0)]


class Mako1Hadoe(SquareCapLeverless):
    """The mako1 layout with the right-hand eight dropped onto the home row.

    The eight action buttons sit in two rows a fixed pitch apart.  In the smash
    layout it is the *bottom* row that lines up with the four directionals, so
    the fingers rest on the lower row and reach up.  Here the whole cluster
    drops by one row pitch, putting the *top* row on the home row instead.

    Everything else — the button coordinates, the thumb clusters, the cap
    shape — is unchanged from :class:`SquareCapLeverless`.
    """

    #: Vertical spacing between the two rows of the right-hand eight.
    row_pitch = 22.0

    right_homerow_affine = SquareCapLeverless.right_homerow_affine * Affine.translation(
        0, -row_pitch
    )


class WideGc(Gccmx):
    """The mako1 layout on Crane's centre row, with matched thumbs and no pinky.

    The hands keep the mako1 spacing and the right hand keeps all eight action
    buttons.  Three changes, and nothing else moves.

    The thumbs become symmetric.  The stock layout is not: the left thumb has
    two buttons, MX and MY, while the right thumb carries a five-button
    c-stick.  Here the right cluster is cut back to its bottom two -- exactly
    the pair the left thumb already has -- so the clusters end up mirror
    images, two buttons under each thumb and the same reach on both sides.

    The centre is :class:`Gccmx`'s, inherited whole: Crane's row of three on a
    20mm pitch where the stock layout has one button, which is the room a Brook
    alongside a ModelS wants for home and share.

    The left hand loses its pinky -- the outermost of its four, 153mm out --
    the same button :class:`FgcLeverless` drops, leaving three directionals
    under the fingers that reach for them.

    Eighteen buttons.  Caps are Frame 1 circles; for the square-keycap version,
    subclass both with the cap shape first::

        class WideGcKeycap(SquareCapLeverless, WideGc):
            pass
    """

    #: The bottom two of the stock c-stick.  ``left_thumb_coords`` is inherited
    #: untouched: it is already the mirror of exactly these two.
    right_thumb_coords = CircleCapLeverless.right_thumb_coords[:2]

    #: The stock four less the last, which is the outermost -- the pinky.
    left_homerow_coords = CircleCapLeverless.left_homerow_coords[:-1]


class FgcLeverless(CircleCapLeverless):
    """Traditional fighting-game layout: one thumb button, eight action buttons."""

    left_thumb_coords = [(0, 0)]
    right_thumb_coords = []
    left_homerow_coords = CircleCapLeverless.left_homerow_coords[:-1]
    right_homerow_coords = [
        (-26.15, -14), (0, 0), (26.65, 0), (53.3, -7),
        (-26.15, -43.0), (0, -29), (26.65, -29), (53.3, -36),
    ]
    misc_coords = [(-26.16, 0), (0, 0), (26.16, 0)]

    right_homerow_affine = Affine.translation(40, 45)
    left_homerow_affine = Affine.translation(-40, 50)
    left_thumb_affine = Affine.translation(0, -30)
    misc_affine = Affine.translation(-90, 57)


class SanwaFgcLeverless(FgcLeverless):
    """The FGC leverless layout, opened up for real Sanwa snap-in buttons.

    The mechanical-switch layouts sit on a ~26mm pitch, which suits 22.5mm
    Frame 1 caps but is too tight for arcade buttons: a 24mm Sanwa button has a
    27mm bezel, so neighbouring buttons would foul each other.  The cluster is
    therefore scaled about the plate origin until the closest pair of centres
    is :attr:`min_pitch` apart -- 30mm, the spacing production leverless boards
    use with 24mm buttons -- and then shifted so the bezels sit centred on the
    plate.

    Scaling the layout as a whole is deliberate.  Scaling only *within* each
    cluster would keep the board small, but the clusters were placed for 22.5mm
    caps, so the gap between the left-hand directionals and the right-hand
    eight closes to about 25mm and those two groups collide.  A uniform scale
    preserves every relative distance, at the cost of a plate a little over an
    inch wider than the mechanical version.

    Button sizes follow the usual convention: the thumb ("up") is a 30mm
    OBSF-30 and everything else is a 24mm OBSF-24.

    Both derived numbers can be pinned: set :attr:`pitch_scale` to fix the
    scale factor, or :attr:`centre_offset` to place the cluster by hand.
    :attr:`layout_affine` is left alone for the caller, as on every other
    layout.
    """

    #: Closest centre-to-centre distance in the scaled layout, mm.
    min_pitch = 30.0
    #: Set to a number to override the scale derived from :attr:`min_pitch`.
    pitch_scale = None
    #: Set to an ``(x, y)`` pair to override the derived centring.
    centre_offset = None

    #: Mounting hole diameter per layout group; groups not listed here use
    #: :attr:`default_hole_diameter`.
    hole_diameters = {"left_thumb": 30.0}
    default_hole_diameter = 24.0
    #: How far a snap-in button's bezel overhangs its hole, on diameter.  What
    #: the layout has to keep clear, as opposed to what it cuts.
    bezel_clearance = 3.0

    @property
    def scale(self):
        """Factor applied to every button centre to reach :attr:`min_pitch`."""
        if self.pitch_scale is not None:
            return float(self.pitch_scale)

        points = np.asarray(self._scaled(1.0), dtype=float)
        gaps = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=-1)
        np.fill_diagonal(gaps, np.inf)
        return self.min_pitch / float(gaps.min())

    @property
    def offset(self):
        """Translation putting the middle of the bezel field on the origin."""
        if self.centre_offset is not None:
            return tuple(self.centre_offset)

        extent = []
        for group in GROUPS:
            radius = (self.hole_diameter(group) + self.bezel_clearance) / 2
            for x, y in self._scaled(self.scale, group):
                extent.append((x - radius, y - radius, x + radius, y + radius))
        if not extent:
            return (0.0, 0.0)

        extent = np.asarray(extent, dtype=float)
        return (
            -(extent[:, 0].min() + extent[:, 2].max()) / 2,
            -(extent[:, 1].min() + extent[:, 3].max()) / 2,
        )

    def _scaled(self, scale, group=None):
        """Group centres scaled about the origin, before centring.

        Goes through :class:`Layout` rather than :meth:`placed` so that the
        scale and offset can be derived from the raw layout without recursing.
        """
        groups = GROUPS if group is None else (group,)
        points = []
        for name in groups:
            points.extend(super().placed(name))
        return [(x * scale, y * scale) for x, y in points]

    def placed(self, group):
        dx, dy = self.offset
        return [(x + dx, y + dy) for x, y in self._scaled(self.scale, group)]

    def hole_diameter(self, group):
        """Mounting hole diameter for the buttons in ``group``."""
        return self.hole_diameters.get(group, self.default_hole_diameter)

    def buttons(self, oversize=0.0):
        """``(x, y, diameter)`` for every button, in final plate coordinates."""
        placed = []
        for group in GROUPS:
            diameter = self.hole_diameter(group) + oversize
            for point in self.placed(group):
                x, y = self.layout_affine * point
                placed.append((x, y, diameter))
        return placed

    def button_geom(self, oversize=0.0):
        """Button openings as geometry, every hole grown by ``oversize``.

        ``oversize`` is what separates the two plates that carry buttons: the
        top plate cuts the nominal mounting hole so the buttons snap into it,
        and the support plate underneath cuts the same holes wider, so it
        clears the button bodies instead of gripping them.
        """
        sketches = []
        for group in GROUPS:
            points = self.placed(group)
            if not len(points):
                continue
            sketches.append(self._sketch(points, self.hole_diameter(group) + oversize))
        if not sketches:
            return cq.Workplane("XY")
        return cq.Workplane("XY").placeSketch(*sketches)

    @property
    def geom(self):
        return self.button_geom()

    def _sketch(self, points, diameter=None):
        if not len(points):
            return None
        if diameter is None:
            diameter = self.default_hole_diameter
        points = [tuple(self.layout_affine * point) for point in points]
        # No intersection fillet: the layout is scaled precisely so that the
        # buttons do not touch.
        return cq.Sketch().push(points).circle(diameter / 2).clean().reset()


class FgcPlus(SanwaFgcLeverless):
    """The FGC layout opened out to a two-handed board, all 24mm buttons.

    Same idea as :class:`FgcLeverless` -- directionals under the left hand, the
    eight action buttons under the right -- but placed on the spacing the smash
    layouts use, with the hands a full 200mm apart instead of 80mm, and a pair
    of thumb buttons under each hand rather than a single one under the left.

    Three things are arranged around the *top* row of the right-hand eight
    being the home row, where the fingers rest:

    * the left hand gets four buttons, not three: the mirror of the right
      hand's second row, pinky included.
    * that mirror is placed one :attr:`row_pitch` above the right hand's
      affine, which puts it level with the right hand's *top* row -- the home
      row -- so both hands rest at the same height.
    * the thumb clusters sit exactly where the smash layouts put MX and MY,
      just inboard of the index finger and well below it.  They stay put when
      the hands go up, so the reach is longer here than on those layouts --
      87mm below the index button against Mako1's 69mm.

    Every button is a 24mm OBSF-24, including the thumbs -- there is no 30mm
    jump button here, because both thumbs have two buttons to reach.

    The three little menu buttons are off by default: on this board they live
    on the back panel, where they are out of the way of a hand that now has to
    cross the whole plate.  Put them back on the face with::

        layout = FgcPlus()
        layout.misc_coords = FgcLeverless.misc_coords

    Dropping them also lets the layout centre properly -- they hung off the
    top left corner and pulled the whole cluster off balance.
    """

    #: Vertical spacing between the two rows of the right-hand eight.
    row_pitch = 29.0

    #: The left hand mirrors the right hand's second row, all four of it.  The
    #: outermost is the pinky button that :class:`FgcLeverless` leaves off.
    left_homerow_coords = np.dot(
        FgcLeverless.right_homerow_coords[4:], [[-1, 0], [0, 1]]
    )

    #: Second thumb button, one button pitch down and out from the first.
    thumb_offset = (21.5, -14.8)

    left_thumb_coords = [(0, 0), thumb_offset]
    right_thumb_coords = [(0, 0), (-thumb_offset[0], thumb_offset[1])]

    #: Hands where the smash layouts put them.  The left one is a row higher
    #: than the right one's affine, which lands it on the right hand's top row.
    left_homerow_affine = Affine.translation(-100, 45 + row_pitch)
    right_homerow_affine = Affine.translation(100, 45)

    #: How far the thumbs follow the hands up, which they have to: with the
    #: home row raised a row and the thumb left where MX and MY sit, the reach
    #: comes out at 87mm against the 69mm of the layout it is copying -- a
    #: whole row further than the thing it is meant to feel like.  15.75 here
    #: is 18.1mm once the layout is scaled for arcade buttons.
    thumb_rise = 15.75

    #: Thumbs where the smash layouts put MX and MY, raised to match the hands.
    left_thumb_affine = CircleCapLeverless.left_thumb_affine * Affine.translation(0, thumb_rise)
    right_thumb_affine = CircleCapLeverless.right_thumb_affine * Affine.translation(0, thumb_rise)

    #: The menu buttons moved to the back panel; see the note above to put
    #: them back on the face.
    misc_coords = []

    #: No 30mm thumb: every button on this board is a 24mm OBSF-24.
    hole_diameters = {}


smashGccmxLayout = Gccmx()
smashF1CapLayout = CircleCapLeverless()
smashKeycapLayout = SquareCapLeverless()
mako1HadoeLayout = Mako1Hadoe()
wideGcLayout = WideGc()
fgcF1CapLayout = FgcLeverless()
sanwaFgcLayout = SanwaFgcLeverless()
fgcPlusLayout = FgcPlus()
