import pathlib
import sys

import cadquery as cq
import pytest
from affine import Affine
from cadquery import exporters

import makoreactor as mr

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from dxf import Drawing  # noqa: E402

REFERENCE_DIR = pathlib.Path(__file__).parent.parent / "notebooks" / "mako1_fgc"


@pytest.fixture(scope="session")
def fgc_assembly():
    """The stack exported to ``notebooks/mako1_fgc`` by ``notebooks/demo.ipynb``."""
    layout = mr.FgcLeverless()
    layout.layout_affine = Affine.translation(0, -13)
    return mr.f1CapMako1.set(
        width=mr.in2mm(11.8),
        height=mr.in2mm(5),
        hole_deltax=300,
        n_modelu=2,
        layout=layout,
    )


@pytest.fixture(scope="session")
def fgc_drawings(fgc_assembly, tmp_path_factory):
    """Generated layers, exported to DXF the same way the notebook does.

    The notebook also clears space for a Brook board in the switchplate and
    faceplate, so the same cut is applied here to make the exports comparable.
    """
    brook = (
        cq.Workplane("XY")
        .rect(100, 50)
        .translate((-45, 0))
        .extrude(10, both=True)
        .translate((-75, -25))
    )

    layers = fgc_assembly.generate()
    layers[2] = layers[2].cut(brook)
    layers[3] = layers[3].cut(brook)

    out = tmp_path_factory.mktemp("fgc")
    drawings = []
    for index, part in enumerate(layers):
        path = out / f"layer{index}.dxf"
        exporters.export(part.edges(">Z"), str(path))
        drawings.append(Drawing(path))
    return drawings


@pytest.fixture(scope="session")
def reference_drawings():
    return [Drawing(REFERENCE_DIR / f"layer{i}.dxf") for i in range(5)]
