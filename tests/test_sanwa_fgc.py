"""The Sanwa-button FGC stack.

The parts are new rather than reconstructed, so there is no reference export to
compare against.  What is asserted instead is the set of constraints the design
was built to satisfy -- the ones in :meth:`SanwaAssembly.checks` -- plus enough
geometry to catch a part that silently stops being manufacturable.
"""

import math

import pytest
from affine import Affine

from makoreactor import layouts
from makoreactor.parts import sanwa_fgc as sf


@pytest.fixture(scope="module")
def stack():
    return sf.sanwaFgc


@pytest.fixture(scope="module")
def solids(stack):
    return dict(zip((type(p).__name__ for p in stack), stack.generate()))


# --- layout ---------------------------------------------------------------

def test_layout_is_scaled_until_the_bezels_clear():
    layout = layouts.SanwaFgcLeverless()
    buttons = layout.buttons()

    closest = min(
        math.hypot(x1 - x0, y1 - y0)
        for i, (x0, y0, _) in enumerate(buttons)
        for x1, y1, _ in buttons[i + 1:]
    )
    assert closest == pytest.approx(layout.min_pitch)
    assert layout.scale > 1  # the mechanical layout is tighter than this


def test_layout_keeps_the_fgc_button_count_and_sizes():
    layout = layouts.SanwaFgcLeverless()
    assert len(layout) == len(layouts.FgcLeverless()) == 15

    diameters = sorted(d for _, _, d in layout.buttons())
    assert diameters == [24.0] * 14 + [30.0]


def test_layout_centres_the_bezels_on_the_plate():
    layout = layouts.SanwaFgcLeverless()
    spans = [
        (x - (d + layout.bezel_clearance) / 2, x + (d + layout.bezel_clearance) / 2,
         y - (d + layout.bezel_clearance) / 2, y + (d + layout.bezel_clearance) / 2)
        for x, y, d in layout.buttons()
    ]
    assert min(s[0] for s in spans) == pytest.approx(-max(s[1] for s in spans))
    assert min(s[2] for s in spans) == pytest.approx(-max(s[3] for s in spans))


def test_layout_affine_is_still_the_callers_to_use():
    """Centring is derived separately, so a shift composes with it."""
    shifted = layouts.SanwaFgcLeverless()
    shifted.layout_affine = Affine.translation(0, -20)

    before = layouts.SanwaFgcLeverless().buttons()
    after = shifted.buttons()
    assert [(x, round(y + 20, 6)) for x, y, _ in after] == [(x, round(y, 6)) for x, y, _ in before]


def test_support_openings_are_wider_than_the_ones_buttons_snap_into():
    layout = layouts.SanwaFgcLeverless()
    clearance = sf.SanwaSupportPlate().button_clearance
    assert [d + clearance for _, _, d in layout.buttons()] == [
        d for _, _, d in layout.buttons(clearance)
    ]


def test_fgc_plus_opens_the_layout_out_to_two_hands():
    """The FGC layout on the smash layouts' spacing, with a pinky button added
    to the left hand and a pair of thumb buttons under each."""
    plus = layouts.FgcPlus()

    assert len(plus.placed("left_homerow")) == 4, "three directionals plus a pinky"
    assert len(plus.placed("right_homerow")) == 8
    assert len(plus.placed("left_thumb")) == len(plus.placed("right_thumb")) == 2
    assert len(plus) == 16
    assert len(layouts.FgcLeverless().placed("left_homerow")) == 3

    # Every button is a 24mm OBSF-24; there is no 30mm thumb button here.
    assert {d for _, _, d in plus.buttons()} == {24.0}

    # The hands sit where the smash layouts put them, not where the FGC one does.
    assert plus.left_homerow_affine.xoff == -100
    assert plus.right_homerow_affine.xoff == 100
    assert abs(layouts.FgcLeverless.right_homerow_affine.xoff) == 40

    # The thumb pairs are mirror images of each other.
    assert sorted(plus.left_thumb_coords) == sorted(
        (-x, y) for x, y in plus.right_thumb_coords
    )
    assert plus.left_thumb_affine.xoff == -plus.right_thumb_affine.xoff


def test_fgc_plus_lines_the_left_hand_up_with_the_home_row():
    """The left cluster is the mirror of the right hand's second row, lifted a
    row, so it lands level with the right hand's top row -- both hands rest at
    the same height."""
    plus = layouts.FgcPlus()

    left = sorted(plus.placed("left_homerow"))
    right = sorted(plus.placed("right_homerow"))
    top_row = sorted(right, key=lambda p: -p[1])[:4]

    assert sorted(round(y, 6) for _, y in left) == sorted(round(y, 6) for _, y in top_row)
    assert sorted(round(-x, 6) for x, _ in left) == sorted(round(x, 6) for x, _ in top_row)

    # It is still the second row's shape, just carried up a row.
    assert plus.left_homerow_affine.yoff - plus.right_homerow_affine.yoff == plus.row_pitch


def test_fgc_plus_thumbs_reach_as_far_as_the_smash_layouts_do():
    """Just inboard of the index finger and the same distance below it.

    The x comes straight from where the smash layouts put MX and MY.  The y
    cannot: this layout's home row sits a row higher, and a thumb left at the
    smash layout's own height ends up reaching 87mm instead of 69mm -- a whole
    row further than the thing it is copying.  So it is lifted to match, and
    what is asserted is the reach, not the affine.
    """
    plus = layouts.FgcPlus()
    smash = layouts.CircleCapLeverless()

    assert plus.left_thumb_affine.xoff == smash.left_thumb_affine.xoff
    assert plus.right_thumb_affine.xoff == smash.right_thumb_affine.xoff
    assert plus.thumb_rise > 0

    def reach(layout):
        """How far the thumb sits below and inboard of the index button."""
        fingers = layout.placed("left_homerow")
        top_row = max(point[1] for point in fingers)
        index = min((p for p in fingers if abs(p[1] - top_row) < 20),
                    key=lambda p: abs(p[0]))
        thumb = max(layout.placed("left_thumb"), key=lambda p: p[1])
        return index[1] - thumb[1], thumb[0] - index[0]

    below, inboard = reach(plus)
    smash_below, smash_inboard = reach(smash)
    assert below == pytest.approx(smash_below, abs=0.5), "same reach as MX and MY"
    assert 0 < inboard < 10, "and only just inboard of the index button"
    # Each finger's two buttons are a row pitch apart -- the rows are staggered
    # finger by finger, so this has to be measured down a column, not overall.
    columns = {}
    for x, y in plus.placed("right_homerow"):
        columns.setdefault(round(x, 3), []).append(y)
    assert len(columns) == 4
    for heights in columns.values():
        assert max(heights) - min(heights) == pytest.approx(plus.row_pitch * plus.scale)

    # And the thumbs sit below everything the fingers rest on.
    assert max(y for _, y in plus.placed("left_thumb")) < min(
        y for _, y in plus.placed("right_homerow")
    )


def test_fgc_plus_drops_the_menu_row_but_can_take_it_back():
    """They live on the back panel here, and having them hang off one corner
    stopped the cluster from centring."""
    plus = layouts.FgcPlus()
    assert plus.placed("misc") == []

    restored = layouts.FgcPlus()
    restored.misc_coords = layouts.FgcLeverless.misc_coords
    assert len(restored.placed("misc")) == 3
    assert len(restored) == len(plus) + 3


def test_fgc_plus_is_balanced_on_its_plate():
    """With the menu row gone the cluster sits square in the middle."""
    plus = layouts.FgcPlus()
    spans = [
        (x - (d + plus.bezel_clearance) / 2, x + (d + plus.bezel_clearance) / 2,
         y - (d + plus.bezel_clearance) / 2, y + (d + plus.bezel_clearance) / 2)
        for x, y, d in plus.buttons()
    ]
    assert min(s[0] for s in spans) == pytest.approx(-max(s[1] for s in spans))
    assert min(s[2] for s in spans) == pytest.approx(-max(s[3] for s in spans))


def test_fgc_plus_buttons_still_clear_each_other():
    plus = layouts.FgcPlus()
    buttons = plus.buttons()
    closest = min(
        math.hypot(x1 - x0, y1 - y0)
        for i, (x0, y0, _) in enumerate(buttons)
        for x1, y1, _ in buttons[i + 1:]
    )
    assert closest == pytest.approx(plus.min_pitch)


def test_fgc_plus_stack_is_a_bigger_board_that_still_checks_out():
    plus, plain = sf.sanwaFgcPlus, sf.sanwaFgc
    top = plus.part(sf.SanwaTopPlate)

    assert not [text for ok, text in plus.checks() if not ok]
    assert top.width > plain.part(sf.SanwaTopPlate).width
    assert isinstance(top.layout, layouts.FgcPlus)

    # The board sits under the right palm, in the corner the layout leaves
    # empty below the action buttons.
    body = plus.part(sf.SanwaBody)
    x, y = body.board_center
    assert x > 0 and y < 0
    right_hand = [bx for bx, by, _ in top.layout.buttons() if bx > 0]
    assert min(right_hand) < x < max(right_hand), "under the right hand, not beside it"

    # It still comes off a bed in two pieces.
    for half in body.halves():
        box = half.val().BoundingBox()
        assert max(box.xlen, box.ylen) <= max(body.print_bed)


# --- fit ------------------------------------------------------------------

def test_the_design_satisfies_its_own_constraints(stack):
    failed = [text for ok, text in stack.checks() if not ok]
    assert not failed


def test_support_openings_are_wide_enough_to_get_a_button_out(stack, solids):
    """They are allowed to merge -- a ring of plate too narrow to get a finger
    into is no use when a snap-in button has to be pinched out -- but the
    plate still has to come out in one piece."""
    support = stack.part(sf.SanwaSupportPlate)
    assert support.button_clearance >= 8.0
    assert len(solids["SanwaSupportPlate"].solids().vals()) == 1

    # Past the guard it really does fall apart, which is why the guard is there.
    import dataclasses

    too_wide = dataclasses.replace(support, button_clearance=9.5)
    assert len(too_wide.generate().solids().vals()) > 1


@pytest.mark.parametrize(
    "field,value,expected",
    [
        # Buttons crowded up against the jack in the middle of the wall.
        ("rear_button_gap", 25.0, "clear each other"),
        # The jack moved under the misc cluster, whose buttons hang into the
        # same space from above.
        ("usb_offset", -114.0, "face buttons"),
        # A wall too thick for a snap tab to grip or a jack screw to reach.
        ("rear_panel_thickness", 4.5, "rear panel"),
        # Not enough wall left above and below a 24mm rear button.
        ("depth", 28.0, "full-thickness wall"),
        # Splitting the body down the middle would saw the jack in half.
        ("split_offset", 0.0, "split runs"),
        # A holder pushed under the button cluster.
        ("board_center", (40.0, 20.0), "board holder clears"),
        # Halves that no longer fit the bed they are printed on.
        ("print_bed", (150.0, 150.0), "printed halves"),
    ],
)
def test_checks_catch_a_broken_body(stack, field, value, expected):
    import dataclasses

    if field == "depth":
        # Every part has a depth; only the body's is meant to change here.
        body = dataclasses.replace(stack.part(sf.SanwaBody), depth=value)
        broken = type(stack)(
            parts=tuple(body if isinstance(p, sf.SanwaBody) else p for p in stack.parts)
        )
    else:
        # The rest are shared: pushing them to one part only would just be
        # caught as the parts disagreeing about where the screws go.
        broken = stack.set(**{field: value})

    failed = [text for ok, text in broken.checks() if not ok]
    assert any(expected in text for text in failed), failed
    with pytest.raises(ValueError):
        broken.check()


def test_plates_screw_into_the_body_on_one_pattern(stack):
    """The two top plates take the whole rim plus the holder; the bottom plate
    takes a subset of the rim, since nothing pushes on it."""
    body = stack.part(sf.SanwaBody)
    rim = sorted(body.mounting_points())
    holder = body.board_screw_points()

    for kind in (sf.SanwaTopPlate, sf.SanwaSupportPlate):
        assert sorted(stack.part(kind).mounting_points()) == sorted(rim + holder)
    assert len(holder) == 2

    low = stack.part(sf.SanwaBottomPlate).mounting_points()
    assert set(low) < set(rim), "a subset of the rim, and fewer of them"
    assert set(body.corner_screw_points()) <= set(low), "corners always kept"


def test_each_corner_takes_one_screw_on_its_chamfer(stack):
    """Rather than one either side of it, which holds the same corner twice."""
    top = stack.part(sf.SanwaTopPlate)
    corners = top.corner_screw_points()
    assert len(corners) == 4
    assert set(corners) <= set(top.mounting_points())

    # Each sits screw_inset in from the chamfer face it is centred on.
    for point in corners:
        assert sf._outline_gap(top, point) == pytest.approx(top.screw_inset, abs=1e-6)


def test_the_fastener_schedule_adds_up(stack):
    """Every screw lands in an insert, and there is an insert for every one."""
    body = stack.part(sf.SanwaBody)
    schedule = dict((text, count) for count, text in stack.fasteners())

    inserts = next(c for t, c in schedule.items() if "insert" in t)
    into_inserts = sum(c for t, c in schedule.items()
                       if "screws" in t and "self-tapping" not in t)
    assert inserts == into_inserts

    expected = (len(body.mounting_points()) + len(body.board_screw_points())
                + len(stack.part(sf.SanwaBottomPlate).mounting_points()))
    assert inserts == expected

    # The screws reach into the insert without bottoming out in it.
    top, support = stack.part(sf.SanwaTopPlate), stack.part(sf.SanwaSupportPlate)
    through = top.depth + support.depth
    length = next(int(t.split("x")[1].split()[0]) for t in schedule if "top plates" in t)
    assert through < length <= through + body.insert_depth


def test_rear_screws_keep_out_of_the_rear_components(stack):
    body = stack.part(sf.SanwaBody)
    boss = body.boss_diameter / 2
    for x in body.rear_screw_points():
        for start, end in body.rear_spans():
            assert x + boss <= start or x - boss >= end, f"boss at {x} fouls {start}..{end}"


def test_the_jack_is_centred_and_the_buttons_split_evenly(stack):
    body = stack.part(sf.SanwaBody)
    assert body.usb_offset == 0.0

    points = body.rear_button_points()
    assert len(points) == body.rear_button_count
    assert points == sorted(points)
    # Mirror image about the jack.
    assert [round(-x, 6) for x in reversed(points)] == [round(x, 6) for x in points]
    left = [x for x in points if x < body.usb_offset]
    assert len(left) == body.rear_button_count // 2


@pytest.mark.parametrize("count", [4, 6])
def test_rear_panel_takes_four_or_six_buttons(stack, count):
    """Six a side closes the pitch up on its own rather than running the
    outermost button off the end of the wall."""
    built = stack.set(rear_button_count=count)
    body = built.part(sf.SanwaBody)

    assert len(body.rear_button_points()) == count
    assert not [text for ok, text in built.checks() if not ok]
    # Still room for a screw between the buttons on each side.
    assert len(body.rear_screw_points()) > 2


def test_the_split_follows_the_rear_panel(stack):
    """Left unset it lands in the bay beside the jack, so moving the buttons
    moves it rather than stranding it in one of them."""
    body = stack.part(sf.SanwaBody)
    assert body.split_offset is None

    for gap in (36.0, 44.0):
        moved = stack.set(rear_button_gap=gap).part(sf.SanwaBody)
        for start, end in moved.rear_spans():
            assert not start < moved.split_x() < end
    assert stack.set(rear_button_gap=44.0).part(sf.SanwaBody).split_x() > body.split_x()

    # Pinning it still works.
    assert stack.set(split_offset=18.0).part(sf.SanwaBody).split_x() == 18.0


def test_rear_buttons_have_release_slots_either_side(stack, solids):
    """A button mounted in a wall has its tabs behind it; the slots are how you
    reach them once the case is shut."""
    body = stack.part(sf.SanwaBody)
    assert body.tab_slot_width > 0 and body.tab_slot_height > 0

    # The slots widen what a rear button needs of the wall, which is what the
    # screw and split placement has to work around.
    assert body._rear_span_radius() >= body.rear_button.hole_diameter / 2 + body.tab_slot_width
    assert body._rear_span_radius() > body._rear_relief_radius()

    # They are really cut: a point just outside the hole, level with it, is air.
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    classifier = BRepClass3d_SolidClassifier(solids["SanwaBody"].val().wrapped)

    def material(x, y, z):
        classifier.Perform(gp_Pnt(x, y, z), 1e-6)
        return classifier.State() in (TopAbs_IN, TopAbs_ON)

    x = body.rear_button_points()[0]
    y = body.height / 2 - 1.5
    z = body.depth / 2
    edge = body.rear_button.hole_diameter / 2 + body.tab_slot_width / 2
    assert not material(x + edge, y, z), "no slot right of the button"
    assert not material(x - edge, y, z), "no slot left of the button"
    assert material(x + edge, y, z + body.tab_slot_height), "slot is not bounded above"


def test_rear_buttons_are_24mm(stack):
    """The 30mm button is the face thumb button; nothing on the back wall is
    bigger than an OBSF-24, which is all a 36mm wall can take."""
    body = stack.part(sf.SanwaBody)
    assert body.rear_button == sf.OBSF24
    assert body.rear_button.hole_diameter == 24.0

    holes = _cylinder_diameters_in_the_back_wall(body)
    assert 24.0 in holes and 30.0 not in holes


def _cylinder_diameters_in_the_back_wall(body):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    solid = body.generate()
    wall = body.height / 2 - body.wall_thickness - 1
    found = set()
    for face in solid.faces().vals():
        if face.Center().y < wall:
            continue
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
            continue
        found.add(round(surface.Cylinder().Radius() * 2, 2))
    return found


def test_top_plate_stays_thin_enough_for_snap_in_buttons(stack):
    top = stack.part(sf.SanwaTopPlate)
    assert sf.OBSF24.fits_panel(top.depth)
    assert sf.OBSF30.fits_panel(top.depth)


def test_d_series_screws_clear_the_bore():
    """Diagonally opposite, and outside the 24mm hole -- unlike the 24mm
    spacing quoted on forums, which would put them inside it."""
    jack = sf.DSERIES
    for dx, dy in jack.screw_offsets:
        assert math.hypot(dx, dy) - jack.screw_diameter / 2 > jack.bore / 2


# --- geometry -------------------------------------------------------------

@pytest.mark.parametrize(
    "name", ["SanwaBottomPlate", "SanwaBody", "SanwaSupportPlate", "SanwaTopPlate"]
)
def test_every_part_is_one_valid_solid(solids, name):
    part = solids[name]
    assert len(part.solids().vals()) == 1, "a part in two pieces cannot be made"
    assert part.val().isValid()
    assert part.val().Volume() > 0


@pytest.mark.parametrize(
    "kind,holes",
    [(sf.SanwaTopPlate, 15), (sf.SanwaSupportPlate, 15), (sf.SanwaBottomPlate, 0)],
)
def test_plates_carry_the_expected_openings(stack, solids, kind, holes):
    part = stack.part(kind)
    # The outline is an octagon with every corner rounded: 8 flats, 8 fillets,
    # a top and a bottom.  Then one face per hole, and for the bottom plate the
    # skirt pocket, which is an octagon of its own with a floor.
    outline = 2 + 2 * len(part.profile_points())
    expected = outline + len(part.mounting_points()) + holes
    if isinstance(part, sf.SanwaSupportPlate):
        # Counting faces says nothing useful here: its openings are wide
        # enough to run into each other, and every intersection splits a face
        # rather than removing one.  What matters is tested next door, in
        # test_support_openings_are_wide_enough_to_get_a_button_out.
        assert len(solids[type(part).__name__].faces().vals()) >= outline
    else:
        assert len(solids[type(part).__name__].faces().vals()) == expected


def test_corners_are_chamfered_and_the_chamfers_rounded(stack, solids):
    top = stack.part(sf.SanwaTopPlate)
    assert len(top.profile_points()) == 8, "a rectangle with its corners cut off"

    blank = top.blank()
    sides = [f for f in blank.faces().vals() if abs(f.normalAt().z) < 1e-6]
    flats = [f for f in sides if f.geomType() == "PLANE"]
    rounds = [f for f in sides if f.geomType() == "CYLINDER"]
    assert len(flats) == 8, "four edges and four chamfers"
    assert len(rounds) == 8, "both ends of every chamfer rounded off"


def test_screws_stay_on_the_plate_once_the_corners_are_cut(stack):
    """The chamfer removes exactly where a square corner would put a screw."""
    top = stack.part(sf.SanwaTopPlate)
    boss = stack.part(sf.SanwaBody).boss_diameter / 2

    for point in top.mounting_points():
        assert sf._outline_gap(top, point) > boss, f"{point} has fallen off the corner"

    # Widening the chamfer cannot strand a screw, because the ring is derived
    # from the outline and moves in with it.
    blunt = stack.set(corner_chamfer=70.0)
    for point in blunt.part(sf.SanwaTopPlate).mounting_points():
        assert sf._outline_gap(blunt.part(sf.SanwaTopPlate), point) > boss

    # The check is still what catches a screw put somewhere it does not fit.
    crowded = stack.set(screw_inset=1.0)
    assert any("screw sits in material" in text
               for ok, text in crowded.checks() if not ok)


def test_body_has_a_skirt_reinforcing_its_open_bottom(stack, solids):
    """The skirt is part of the printed body, not the plate under it: the body
    is open underneath, and this is what ties its walls together."""
    body = stack.part(sf.SanwaBody)
    bottom = stack.part(sf.SanwaBottomPlate)

    assert not hasattr(bottom, "skirt_width"), "the skirt belongs to the body"
    assert bottom.flat, "so the bottom plate stays a plain cut plate"

    # It reaches past the bosses it is tying together, and stops short of the
    # rear button reliefs above it.
    assert body.skirt_width > body.boss_diameter / 2
    assert body.skirt_depth <= body.depth / 2 - body._rear_relief_radius()

    # Its opening is chamfered and rounded like the outline, at its own scale.
    assert len(body.profile_points(body.skirt_opening(), body.skirt_chamfer)) == 8

    # And it is really there: the body weighs more than the same walls without.
    import dataclasses

    bare = dataclasses.replace(body, skirt_width=0.0)
    assert solids["SanwaBody"].val().Volume() > bare.generate().val().Volume() * 1.05


def test_board_can_be_fitted_through_the_skirt(stack):
    """The board goes in from underneath, so the opening the skirt leaves has
    to be bigger than the board."""
    body = stack.part(sf.SanwaBody)
    x0, y0, x1, y1 = sf._board_extent(body)
    for corner in [(x, y) for x in (x0, x1) for y in (y0, y1)]:
        assert sf._outline_gap(body, corner, body.skirt_opening()) > 0


def test_plate_outlines_match(stack, solids):
    boxes = [solids[type(p).__name__].val().BoundingBox() for p in stack]
    assert {(round(b.xlen, 6), round(b.ylen, 6)) for b in boxes} == {(320.0, 200.0)}


def test_stack_height_is_the_sum_of_its_layers(stack):
    assert stack.height() == pytest.approx(3.0 + 36.0 + 6.0 + 3.0)


def test_body_splits_into_two_printable_pieces(stack, solids):
    body = stack.part(sf.SanwaBody)
    left, right = body.halves(solids["SanwaBody"])

    for half in (left, right):
        assert len(half.solids().vals()) == 1, "a half that falls apart cannot be printed"
        assert half.val().isValid()
    # Nothing is lost or double counted at the cut.
    assert left.val().Volume() + right.val().Volume() == pytest.approx(
        solids["SanwaBody"].val().Volume()
    )
    # Each piece fits on the bed, which the whole body does not.
    for half in (left, right):
        box = half.val().BoundingBox()
        assert max(box.xlen, box.ylen) <= max(body.print_bed)
    assert body.width > max(body.print_bed)


def test_the_split_misses_everything_it_must_not_cut(stack):
    body = stack.part(sf.SanwaBody)
    split = body.split_x()

    assert split != body.usb_offset
    for start, end in body.rear_spans():
        assert not start < split < end
    for x, _ in body.mounting_points():
        assert abs(x - split) > body.boss_diameter / 2
    x0, _, x1, _ = body.board_holder_extent()
    assert not x0 < split < x1


def test_board_hangs_from_the_top_of_the_cavity(stack):
    body = stack.part(sf.SanwaBody)
    holder_underside = body.depth - body.board_holder_thickness
    board_top = holder_underside - body.board_standoff

    assert board_top > body.depth / 2, "the board should be up under the lid, not on the floor"
    # The screws that tie the top plates down land on the slab, not in mid-air.
    x0, y0, x1, y1 = body.board_holder_extent()
    for x, y in body.board_screw_points():
        assert x0 < x < x1 and y0 < y < y1


def test_walls_are_thick_enough_to_carry_an_insert(stack):
    body = stack.part(sf.SanwaBody)
    assert body.wall_thickness >= 8.0
    # The boss is mostly buried in the wall, so what matters is that the
    # insert is not breaking out of it.
    assert body.boss_diameter / 2 - body.insert_diameter / 2 >= 3.0
    assert body.rear_panel_thickness < body.wall_thickness


def test_body_is_hollow_and_open_underneath(stack, solids):
    body = stack.part(sf.SanwaBody)
    solid = solids["SanwaBody"].val()
    # A solid slab of the same outline would be far heavier; the body is walls,
    # bosses and a shelf.
    assert solid.Volume() < 0.5 * body.width * body.height * body.depth


def test_assembling_the_stack_places_each_layer_above_the_last(stack):
    assembly = stack.assemble()
    zs = [child.loc.toTuple()[0][2] for child in assembly.children]
    assert zs == sorted(zs)
    assert zs[-1] == pytest.approx(3.0 + 36.0 + 6.0)
