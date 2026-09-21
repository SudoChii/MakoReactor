import numpy as np
import pytest
from affine import Affine

from makoreactor import layouts


def test_fgc_layout_matches_reference_button_centres():
    """Centres cut into ``notebooks/mako1_fgc/layer3.dxf``."""
    layout = layouts.FgcLeverless()
    layout.layout_affine = Affine.translation(0, -13)

    expected = [
        (-116.16, 44.0), (-90.0, 44.0), (-63.84, 44.0),
        (-66.65, 11.8), (-40.0, 15.0), (-13.85, 3.25),
        (0.0, -43.0),
        (13.85, -11.0), (13.85, 18.0), (40.0, 3.0), (40.0, 32.0),
        (66.65, 3.0), (66.65, 32.0), (93.3, -4.0), (93.3, 25.0),
    ]

    got = sorted((round(x, 2), round(y, 2)) for x, y in layout.layout)
    assert got == sorted(expected)


@pytest.mark.parametrize(
    "cls,count",
    [
        (layouts.CircleCapLeverless, 20),
        (layouts.SquareCapLeverless, 20),
        (layouts.Gccmx, 22),
        (layouts.Mako1Hadoe, 20),
        (layouts.WideGc, 18),
        (layouts.FgcLeverless, 15),
    ],
)
def test_button_counts(cls, count):
    assert len(cls()) == count


def _rows(layout, group):
    """The ``(x, y)`` of a group, rounded, sorted by x."""
    return sorted((round(x, 2), round(y, 2)) for x, y in layout.placed(group))


def _ys(layout, group):
    """The y coordinates of a group, rounded, ascending."""
    return sorted(round(y, 2) for _, y in layout.placed(group))


HOME_ROW_YS = [16.55, 24.25, 32.8, 36.0]


def test_smash_layout_rests_on_the_lower_row():
    """In the stock layout the *bottom* row of the eight is the home row."""
    layout = layouts.SquareCapLeverless()

    right, left = _ys(layout, "right_homerow"), _ys(layout, "left_homerow")

    assert left == HOME_ROW_YS
    assert right[:4] == HOME_ROW_YS      # lower four align with the directionals
    assert right[4:] != HOME_ROW_YS      # upper four sit a row above


def test_mako1_hadoe_brings_the_top_row_onto_the_home_row():
    """Mako1Hadoe drops the right-hand eight by one row pitch."""
    layout = layouts.Mako1Hadoe()

    right, left = _ys(layout, "right_homerow"), _ys(layout, "left_homerow")

    assert left == HOME_ROW_YS
    assert right[4:] == HOME_ROW_YS      # now it is the *upper* four that align
    assert right[:4] != HOME_ROW_YS


def test_mako1_hadoe_only_moves_the_right_homerow():
    """Everything except the right-hand eight is untouched."""
    stock, hadoe = layouts.SquareCapLeverless(), layouts.Mako1Hadoe()

    for group in layouts.GROUPS:
        if group == "right_homerow":
            continue
        assert _rows(stock, group) == _rows(hadoe, group), group


def test_mako1_hadoe_shift_is_exactly_one_row_pitch():
    stock, hadoe = layouts.SquareCapLeverless(), layouts.Mako1Hadoe()

    shifted = np.array(_rows(hadoe, "right_homerow")) - np.array(_rows(stock, "right_homerow"))
    np.testing.assert_allclose(shifted, np.tile([0.0, -hadoe.row_pitch], (8, 1)))


def test_mako1_hadoe_keeps_square_caps():
    assert isinstance(layouts.Mako1Hadoe(), layouts.SquareCapLeverless)
    assert layouts.mako1HadoeLayout.cap_dimensions == (20.5, 20.5)


def test_widegc_thumb_clusters_are_mirrored_pairs():
    """Both thumbs get the same two buttons, one cluster the mirror of the other."""
    layout = layouts.WideGc()

    left, right = layout.placed("left_thumb"), layout.placed("right_thumb")

    assert len(left) == len(right) == 2
    assert sorted((round(-x, 2), round(y, 2)) for x, y in left) == _rows(layout, "right_thumb")


def test_widegc_thumbs_are_the_bottom_of_the_stock_cluster():
    """The pair kept is the lowest two of the stock five-button c-stick."""
    stock, wide = layouts.CircleCapLeverless(), layouts.WideGc()

    kept = _rows(wide, "right_thumb")

    assert set(kept) <= set(_rows(stock, "right_thumb"))
    assert sorted(y for _, y in kept) == _ys(stock, "right_thumb")[:2]


def test_widegc_centre_is_cranes_row_of_three():
    """The single centre button becomes the GCCMX row, inherited whole."""
    wide = layouts.WideGc()

    assert len(layouts.CircleCapLeverless().misc_coords) == 1
    assert isinstance(wide, layouts.Gccmx)
    assert _rows(wide, "misc") == _rows(layouts.Gccmx(), "misc")
    assert len(wide.placed("misc")) == 3


def test_widegc_centre_sits_where_the_stock_button_did():
    """The row of three is centred on the single button it replaces."""
    stock, wide = layouts.CircleCapLeverless(), layouts.WideGc()

    np.testing.assert_allclose(
        np.array(wide.placed("misc")).mean(axis=0), stock.placed("misc")[0]
    )


def test_widegc_drops_the_left_pinky():
    """The left hand keeps three of its four: the outermost comes off."""
    stock, wide = layouts.CircleCapLeverless(), layouts.WideGc()

    kept, before = _rows(wide, "left_homerow"), _rows(stock, "left_homerow")

    assert len(kept) == 3
    assert set(kept) < set(before)
    dropped, = set(before) - set(kept)
    assert dropped[0] == min(x for x, _ in before)   # the farthest out


def test_widegc_drops_the_same_pinky_as_the_fgc_layout():
    stock, wide = layouts.CircleCapLeverless(), layouts.WideGc()
    fgc_coords = layouts.FgcLeverless.left_homerow_coords

    np.testing.assert_allclose(wide.left_homerow_coords, fgc_coords)
    assert len(wide.left_homerow_coords) == len(stock.left_homerow_coords) - 1


def test_widegc_leaves_the_right_hand_and_the_left_thumb_alone():
    """Only the three groups it sets move; the rest is the stock layout."""
    stock, wide = layouts.CircleCapLeverless(), layouts.WideGc()

    for group in ("right_homerow", "left_thumb"):
        assert _rows(stock, group) == _rows(wide, group), group


def test_empty_group_is_skipped():
    layout = layouts.FgcLeverless()
    assert layout.right_thumb_coords == []
    assert layout.placed("right_thumb") == []


def test_unknown_group_rejected():
    with pytest.raises(ValueError, match="unknown layout group"):
        layouts.FgcLeverless().placed("nope")


def test_malformed_coords_rejected():
    class Broken(layouts.FgcLeverless):
        misc_coords = [(1, 2, 3)]

    with pytest.raises(ValueError, match="sequence of"):
        Broken().placed("misc")


def test_multiplication_does_not_mutate_the_original():
    layout = layouts.FgcLeverless()
    before = list(layout.layout)

    shifted = layout * Affine.translation(10, 0)

    assert list(layout.layout) == before
    assert shifted is not layout
    np.testing.assert_allclose(
        np.array(shifted.layout) - np.array(before), np.tile([10.0, 0.0], (len(before), 1))
    )


def test_rmul_applies_before_the_layout_affine():
    layout = layouts.FgcLeverless()
    shifted = Affine.translation(0, 5) * layout
    np.testing.assert_allclose(
        np.array(shifted.layout) - np.array(layout.layout),
        np.tile([0.0, 5.0], (len(layout), 1)),
    )


def test_iteration_and_tolist_agree():
    layout = layouts.Gccmx()
    assert list(layout) == layout.tolist()
    assert len(layout.tolist()) == len(layout)


@pytest.mark.parametrize(
    "cls",
    [
        layouts.CircleCapLeverless,
        layouts.SquareCapLeverless,
        layouts.FgcLeverless,
        layouts.WideGc,
    ],
)
def test_geom_cuts_a_valid_plate(cls):
    """``geom`` is a cutter; the plate it leaves behind is what has to be valid."""
    import cadquery as cq

    layout = cls()
    plate = cq.Workplane("XY").rect(400, 200).extrude(3)
    cut = plate.cut(layout.geom.extrude(9).translate((0, 0, -3)))

    assert cut.val().isValid()
    assert cut.val().Volume() < plate.val().Volume()


def test_thumb_cluster_caps_are_only_just_touching():
    """Documents a sharp edge in the smash layout.

    The diagonal c-stick caps overlap by ~0.03mm, so ``intersection_fillet``
    produces a degenerate face and the cluster encloses a loose island.  The
    geometry still cuts correctly, but ``geom.extrude()`` alone is not a valid
    solid.  Kept as a test so the behaviour is noticed if the layout changes.
    """
    import cadquery as cq

    layout = layouts.CircleCapLeverless()
    thumb = cq.Workplane("XY").placeSketch(layout._sketch(layout.placed("right_thumb")))
    assert not thumb.extrude(1).val().isValid()
