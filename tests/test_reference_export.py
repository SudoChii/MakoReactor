"""Regression tests against the DXF exports checked in under ``notebooks/``.

``notebooks/mako1_fgc/layer{0..4}.dxf`` were cut from real material, so they are
treated as the specification for the geometry this library produces.
"""

import pytest

LAYERS = [
    (0, "Base"),
    (1, "WireSpaceModelU"),
    (2, "Switchplate"),
    (3, "F1CapFaceplate"),
    (4, "Backplate"),
]



@pytest.mark.parametrize("index,name", LAYERS)
def test_layer_outline_matches_reference(index, name, fgc_drawings, reference_drawings):
    assert fgc_drawings[index].size == reference_drawings[index].size, name
    assert fgc_drawings[index].bounds == reference_drawings[index].bounds, name


@pytest.mark.parametrize("index,name", LAYERS)
def test_layer_holes_match_reference(index, name, fgc_drawings, reference_drawings):
    """Mounting holes and button openings, to the hundredth of a millimetre."""
    assert fgc_drawings[index].circles == reference_drawings[index].circles, name


@pytest.mark.parametrize("index,name", LAYERS)
def test_layer_straight_edges_match_reference(index, name, fgc_drawings, reference_drawings):
    generated = fgc_drawings[index].counts["LINE"]
    reference = reference_drawings[index].counts["LINE"]
    assert generated == reference, name


@pytest.mark.parametrize("index,name", LAYERS)
def test_layer_arcs_match_reference(index, name, fgc_drawings, reference_drawings):
    """Every fillet and relief, to the hundredth of a millimetre."""
    generated = set(fgc_drawings[index].arcs)
    reference = set(reference_drawings[index].arcs)

    assert not generated - reference, f"{name}: unexpected arcs {sorted(generated - reference)}"
    assert not reference - generated, f"{name}: missing arcs {sorted(reference - generated)}"


@pytest.mark.parametrize("index,name", LAYERS)
def test_layer_is_identical_to_reference(index, name, fgc_drawings, reference_drawings):
    """The whole drawing: entity counts, outline, holes, and arcs."""
    generated, reference = fgc_drawings[index], reference_drawings[index]

    assert dict(generated.counts) == dict(reference.counts), name
    assert generated.bounds == reference.bounds, name
    assert generated.circles == reference.circles, name
    assert generated.arcs == reference.arcs, name
