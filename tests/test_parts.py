import pathlib

import pytest

from makoreactor import layouts
from makoreactor.parts import layered_leverless as ll


def test_in2mm():
    assert ll.in2mm(1) == 25.4
    assert ll.in2mm(11.8) == pytest.approx(299.72)


def test_narrow_plate_keeps_only_corner_holes():
    """11.8" wide with a 300mm pitch: the second ring would fall off the plate."""
    part = ll.Base(width=ll.in2mm(11.8), height=ll.in2mm(5), hole_deltax=300)
    points = sorted((round(x, 2), round(y, 2)) for x, y in part.mounting_points())
    assert points == [(-137.36, -51.0), (-137.36, 51.0), (137.36, -51.0), (137.36, 51.0)]


def test_wide_plate_picks_up_an_inner_ring():
    """13.5" wide with a 275mm pitch, as in notebooks/artifacts/mako1."""
    part = ll.Base(width=ll.in2mm(13.5), height=ll.in2mm(5.9), hole_deltax=275)
    points = sorted((round(x, 2), round(y, 2)) for x, y in part.mounting_points())
    assert points == [
        (-158.95, -62.43), (-158.95, 62.43),
        (-21.45, -62.43), (-21.45, 62.43),
        (21.45, -62.43), (21.45, 62.43),
        (158.95, -62.43), (158.95, 62.43),
    ]


def test_mounting_points_are_deduplicated():
    part = ll.Base()
    assert len(part.mounting_points()) == len(set(part.mounting_points()))


def test_set_only_applies_parameters_a_part_accepts():
    """``wall_thickness`` exists on the spacer but not on the other layers."""
    stack = ll.f1CapMako1.set(width=300, wall_thickness=12)

    assert [p.width for p in stack] == [300] * len(stack)
    spacer = next(p for p in stack if isinstance(p, ll.WireSpaceModelU))
    assert spacer.wall_thickness == 12


def test_set_returns_a_new_assembly():
    original_width = ll.f1CapMako1.parts[0].width
    ll.f1CapMako1.set(width=999)
    assert ll.f1CapMako1.parts[0].width == original_width


def _arcs_of(part, tmp_path):
    """Top-face arcs of a generated part, as ``(radius, x, y)``."""
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from cadquery import exporters

    from dxf import Drawing

    path = tmp_path / "part.dxf"
    exporters.export(part.generate().edges(">Z"), str(path))
    return Drawing(path).arcs


def test_usbc_reliefs_are_tangent_to_the_pocket_walls(tmp_path):
    """The semicircles that let the breakout PCB be lifted out of its pocket.

    Each is centred on the pocket's top edge and tangent to a side wall, so only
    its top half breaks the outline — the "semicircle" in the reference DXFs.
    """
    part = ll.WireSpaceModelU(
        width=ll.in2mm(11.8), height=ll.in2mm(5), hole_deltax=300,
        layout=layouts.FgcLeverless(),
    )

    pocket_top = part.height / 2 - part.usbc_pocket_inset
    offset = part.usbc_pocket_width / 2 - part.usbc_relief_radius

    reliefs = [a for a in _arcs_of(part, tmp_path) if a[0] == part.usbc_relief_radius]
    assert sorted(reliefs) == [
        (5.0, -offset, pocket_top),
        (5.0, offset, pocket_top),
    ]


def test_usbc_pocket_matches_the_pcb_layer_1_example(tmp_path):
    """notebooks/artifacts/pcb_layer_1.dxf: reliefs at (+-5.5, 65.9), r=5.

    A different plate, but the same feature, so it pins the parameterisation
    rather than one set of numbers.
    """
    part = ll.WireSpaceModelU(
        width=ll.in2mm(14), height=ll.in2mm(6), hole_diameter=8, fillet_radius=3,
        usbc_pocket_width=21, usbc_pocket_depth=9.5, usbc_pocket_inset=10.3,
        usbc_fillet=0, layout=layouts.FgcLeverless(),
    )

    reliefs = [a for a in _arcs_of(part, tmp_path) if a[0] == 5.0]
    assert sorted(reliefs) == [(5.0, -5.5, 65.9), (5.0, 5.5, 65.9)]


def test_usbc_slot_is_narrower_than_the_pocket():
    """The connector pokes through a slot; the board behind it sits wider."""
    part = ll.WireSpaceModelU()
    assert part.usbc_slot_width < part.usbc_pocket_width
    assert part.usbc_throat_width < part.usbc_pocket_width
    assert part.usbc_relief_radius * 2 <= part.usbc_pocket_width


def test_wire_space_depth_scales_with_modelu_count():
    one = ll.WireSpaceModelU(n_modelu=1)
    two = ll.WireSpaceModelU(n_modelu=2)
    assert two.part_depth() == pytest.approx(2 * one.part_depth())

    bounds = two.generate().val().BoundingBox()
    assert bounds.zlen == pytest.approx(two.part_depth())


ALL_PARTS = [
    ll.Base, ll.WireSpaceModelU, ll.Switchplate,
    ll.F1CapFaceplate, ll.KeycapFaceplate, ll.Backplate,
]


@pytest.mark.parametrize("cls", ALL_PARTS)
def test_every_part_generates_a_valid_plate(cls):
    part = cls(width=ll.in2mm(11.8), height=ll.in2mm(5), hole_deltax=300,
               layout=layouts.FgcLeverless())
    solid = part.generate().val()

    assert solid.isValid()
    assert len(solid.Solids()) == 1, f"{cls.__name__} fell apart into loose pieces"

    bounds = solid.BoundingBox()
    assert bounds.xlen == pytest.approx(part.width, abs=1e-6)
    assert bounds.ylen == pytest.approx(part.height, abs=1e-6)
    assert bounds.zlen == pytest.approx(
        part.part_depth() if isinstance(part, ll.WireSpaceModelU) else part.depth
    )


@pytest.mark.parametrize("cls", ALL_PARTS)
def test_default_sized_parts_are_valid(cls):
    """The default 14x6" plate is the size the default smash layout is drawn for."""
    solid = cls().generate().val()
    assert solid.isValid()

    biggest = max(solid.Solids(), key=lambda s: s.Volume())
    bounds = biggest.BoundingBox()
    assert bounds.xlen == pytest.approx(cls().width, abs=1e-6)
    assert bounds.ylen == pytest.approx(cls().height, abs=1e-6)


@pytest.mark.parametrize("cls", [ll.F1CapFaceplate, ll.KeycapFaceplate, ll.Backplate])
def test_smash_thumb_cluster_leaves_a_loose_island(cls):
    """The c-stick caps enclose a sliver that is not attached to the plate.

    Faithful to the original design, but it means a cut faceplate has a small
    loose piece.  Layouts without a right thumb cluster (FgcLeverless) do not.
    """
    solids = cls().generate().val().Solids()
    assert len(solids) == 2
    assert min(s.Volume() for s in solids) < 500  # mm^3, a sliver

    fgc = cls(layout=layouts.FgcLeverless()).generate().val()
    assert len(fgc.Solids()) == 1


def test_create_is_an_alias_for_generate():
    part = ll.Base(width=200, height=120)
    assert part.create().val().Volume() == pytest.approx(part.generate().val().Volume())


def test_keycap_faceplate_defaults_to_the_square_layout():
    assert isinstance(ll.KeycapFaceplate().layout, layouts.SquareCapLeverless)
    assert isinstance(ll.F1CapFaceplate().layout, layouts.CircleCapLeverless)


def test_assembly_stacks_parts_along_z():
    stack = ll.f1CapMako1.set(width=ll.in2mm(11.8), height=ll.in2mm(5), hole_deltax=300)
    assembled = stack.assemble()

    assert len(assembled.children) == len(stack)
    zs = [child.loc.toTuple()[0][2] for child in assembled.children]
    assert zs == sorted(zs)
    assert zs[0] == 0

    # Layers sit flush: each starts where the one below it ends.
    depths = [p.part_depth() if isinstance(p, ll.WireSpaceModelU) else p.depth for p in stack]
    assert zs[1] == pytest.approx(depths[0])


def test_assembly_gap_explodes_the_stack():
    stack = ll.f1CapMako1.set(width=ll.in2mm(11.8), height=ll.in2mm(5), hole_deltax=300)

    flush = [c.loc.toTuple()[0][2] for c in stack.assemble().children]
    exploded = [c.loc.toTuple()[0][2] for c in stack.assemble(gap=10).children]

    for index, (a, b) in enumerate(zip(flush, exploded)):
        assert b == pytest.approx(a + 10 * index)


def test_assembly_colors_cycle_and_can_be_overridden():
    stack = ll.f1CapMako1.set(width=ll.in2mm(11.8), height=ll.in2mm(5), hole_deltax=300)

    default = stack.assemble()
    assert all(child.color is not None for child in default.children)

    recolored = stack.assemble(colors=["red", "blue"])
    tuples = [child.color.toTuple() for child in recolored.children]
    assert tuples[0] == tuples[2] == tuples[4]
    assert tuples[1] == tuples[3]
    assert tuples[0] != tuples[1]
