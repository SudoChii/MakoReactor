"""The Brook stack: room for the board, and four screws to hang it from.

``brookMako1`` differs from ``f1CapMako1`` in two layers only, so most of what
is worth asserting is that the two layers agree with each other and with the
board they were sized around.
"""

import cadquery as cq
import pytest

import makoreactor as mr
from makoreactor.parts.sanwa_fgc import SanwaBody


def solid_at(shape, x, y, size=1.0):
    """Is there material at ``(x, y)``, anywhere through the plate's depth?"""
    probe = (
        cq.Workplane("XY")
        .center(x, y)
        .rect(size, size)
        .extrude(100, both=True)
    )
    return probe.intersect(shape).val().Volume() > 0


@pytest.fixture(scope="module")
def stack():
    return mr.brookMako1


@pytest.fixture(scope="module")
def layers(stack):
    return stack.generate()


def test_every_fit_check_passes(stack):
    failed = [text for ok, text in stack.checks() if not ok]
    assert failed == []


def test_check_raises_when_the_board_does_not_fit(stack):
    """A board too tall for the switchplate to swallow is caught, not cut."""
    tall = mr.brookMako1.set(board=mr.BrookBoard(component_height=30.0))

    with pytest.raises(ValueError, match="fit check failed"):
        tall.check()


def test_board_dimensions_agree_with_the_sanwa_stack():
    """Both stacks house the same board, so both must assume the same numbers."""
    board = mr.BrookBoard()

    assert board.size == SanwaBody.board_size
    assert board.hole_inset == SanwaBody.board_hole_inset


def test_hole_pattern_is_the_board_less_two_insets():
    board = mr.BrookBoard()

    assert board.hole_pitch() == pytest.approx((89.01, 38.01))
    assert len(board.hole_offsets()) == 4
    assert sorted(board.hole_offsets()) == sorted(
        (sx * 44.505, sy * 19.005) for sx in (-1, 1) for sy in (-1, 1)
    )


def test_all_five_layers_are_valid_solids(layers):
    assert len(layers) == 5
    for part, solid in zip(mr.brookMako1.parts, layers):
        assert solid.val().isValid(), type(part).__name__


def test_wire_space_is_two_thicknesses_of_stock(stack, layers):
    space = stack.part(mr.BrookWireSpace)

    assert space.spacers() == 2
    assert space.part_depth() == pytest.approx(2 * space.depth)
    assert layers[1].val().BoundingBox().zlen == pytest.approx(space.part_depth())


def test_wire_space_grows_for_a_board_one_spacer_cannot_hold():
    """``n_modelu`` sets the floor, not the ceiling: a thick board raises it."""
    thin = mr.BrookWireSpace(n_modelu=1)
    thick = mr.BrookWireSpace(n_modelu=1, board=mr.BrookBoard(below_board=8.0))

    assert thin.spacers() == 1
    assert thick.spacers() == 2
    # and the layer is actually cut at that depth, not just reported
    assert thick.generate().val().BoundingBox().zlen == pytest.approx(thick.part_depth())


def test_standoffs_and_relief_account_for_the_whole_board(stack):
    """Standoff plus what hangs below fills the wire space; the rest sticks up."""
    space = stack.part(mr.BrookWireSpace)
    board = space.board

    assert space.standoff_length() + board.below_switchplate() == pytest.approx(
        space.part_depth()
    )
    assert space.relief_depth() == pytest.approx(
        board.component_height - space.standoff_length()
    )


def test_relief_is_shallow_enough_for_the_switchplate_to_swallow(stack):
    """The components must not reach past the switchplate into the faceplate."""
    space, switch = stack.part(mr.BrookWireSpace), stack.part(mr.BrookSwitchplate)

    assert 0 < space.relief_depth() <= switch.depth


def test_switchplate_screw_holes_are_open(stack, layers):
    switch = stack.part(mr.BrookSwitchplate)

    for x, y in switch.board_hole_points():
        assert not solid_at(layers[2], x, y, size=0.5), (x, y)


def test_switchplate_window_is_open_and_the_rim_is_not(stack, layers):
    switch = stack.part(mr.BrookSwitchplate)
    cx, cy = switch.board_center
    width, height = switch.relief_size()

    assert not solid_at(layers[2], cx, cy)                    # middle of the window
    assert switch.rim_to_hole() > 0
    # material between the window edge and the screw hole, on both axes
    assert solid_at(layers[2], cx + width / 2 + switch.rim_to_hole() / 2, cy, size=0.5)
    assert solid_at(layers[2], cx, cy + height / 2 + switch.rim_to_hole() / 2, size=0.5)


def test_switchplate_window_stays_inside_the_board(stack):
    """The window is the board pulled in by the rim, so it never overhangs."""
    switch = stack.part(mr.BrookSwitchplate)
    width, height = switch.relief_size()

    assert width == pytest.approx(switch.board.size[0] - 2 * switch.board_rim)
    assert height == pytest.approx(switch.board.size[1] - 2 * switch.board_rim)
    assert width < switch.board.size[0] and height < switch.board.size[1]


def test_switchplate_relief_can_be_turned_off(stack):
    """With a deep enough wire space the plate is plain but for the screws."""
    plain = mr.brookMako1.set(board_relief=False)
    layer = plain.part(mr.BrookSwitchplate).generate()
    switch = plain.part(mr.BrookSwitchplate)
    cx, cy = switch.board_center

    assert solid_at(layer, cx, cy)                            # window gone
    for x, y in switch.board_hole_points():                   # screws stay
        assert not solid_at(layer, x, y, size=0.5)


def test_faceplate_and_backplate_are_untouched(layers):
    """Only two layers differ from the plain stack."""
    plain = mr.f1CapMako1.set(layout=mr.WideGc(), n_modelu=2).generate()

    for index in (0, 3, 4):
        assert layers[index].val().Volume() == pytest.approx(
            plain[index].val().Volume()
        )


def test_switchplate_only_removes_material(layers):
    """The board features are cuts, so the plate can only get lighter."""
    plain = mr.Switchplate(layout=mr.WideGc()).generate()

    assert layers[2].val().Volume() < plain.val().Volume()


def test_part_lookup_works_on_both_assembly_kinds():
    """``part()`` lives on LayeredAssembly now; both stacks use the same one."""
    assert isinstance(mr.brookMako1.part(mr.BrookWireSpace), mr.BrookWireSpace)
    assert isinstance(mr.sanwaFgc.part(mr.SanwaTopPlate), mr.SanwaTopPlate)

    with pytest.raises(LookupError, match="no BrookWireSpace"):
        mr.f1CapMako1.part(mr.BrookWireSpace)


def test_stack_height_counts_the_deep_wire_space(stack):
    """``height`` has to use the wire space's real depth, not its stock thickness."""
    space = stack.part(mr.BrookWireSpace)
    plates = [p.depth for p in stack.parts if not isinstance(p, mr.BrookWireSpace)]

    assert stack.height() == pytest.approx(sum(plates) + space.part_depth())


def test_every_stack_has_a_default_layout_it_actually_fits():
    """The CLI used to pick the default layout from whether a stack self-sizes.

    That handed the Brook stack the Sanwa layout, whose buttons land on top of
    the board.  Each stack names the layout it was designed around instead.
    """
    from makoreactor import __main__ as cli

    assert set(cli.STACK_LAYOUT) == set(cli.STACKS)
    assert set(cli.STACK_LAYOUT.values()) <= set(cli.LAYOUTS)
    assert cli.STACK_LAYOUT["brook"] == "widegc"


def test_the_brook_stack_refuses_a_layout_that_lands_on_the_board():
    """The FGC layout puts its action buttons straight through the board."""
    from makoreactor import __main__ as cli

    clash = mr.brookMako1.set(layout=cli.LAYOUTS["fgc"]())
    failed = [text for ok, text in clash.checks() if not ok]

    assert any("switch mount" in text for text in failed)
