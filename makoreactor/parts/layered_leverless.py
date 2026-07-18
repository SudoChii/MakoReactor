"""Parametric layered leverless controller parts."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Iterable, Optional, Sequence

import cadquery as cq

from makoreactor.layouts import CircleCapLeverless, Layout, SquareCapLeverless


def in2mm(value: float) -> float:
    return value * 25.4


def _replace_part(part, **kwargs):
    valid = {f.name for f in fields(part)}
    return replace(part, **{k: v for k, v in kwargs.items() if k in valid})


@dataclass
class PlatePart:
    width: float = field(default_factory=lambda: in2mm(14))
    height: float = field(default_factory=lambda: in2mm(6))
    depth: float = 3.175
    hole_diameter: float = 10
    hole_offset: float = 25
    hole_deltax: float = 275
    hole_deltay: float = 275
    fillet_radius: float = 8
    n_modelu: int = 2
    layout: Layout = field(default_factory=CircleCapLeverless)

    def _edge_margin(self) -> float:
        return self.hole_offset / 2

    def mounting_points(self) -> list[tuple[float, float]]:
        edge = self._edge_margin()
        outer_x = self.width / 2 - edge
        y_pos = self.height / 2 - edge
        xs: list[float]

        if self.n_modelu >= 2:
            inner_x = outer_x - self.hole_deltax / 2
            xs = [-outer_x, -inner_x, inner_x, outer_x] if inner_x > 0 else [-outer_x, outer_x]
        else:
            xs = [-outer_x, outer_x]

        return [(x, y) for x in xs for y in (y_pos, -y_pos)]

    def _plate(self) -> cq.Workplane:
        plate = cq.Workplane("XY").rect(self.width, self.height).extrude(self.depth)
        try:
            plate = plate.edges("|Z").fillet(self.fillet_radius)
        except Exception:
            pass
        return plate

    def _cut_mounting_holes(self, plate: cq.Workplane) -> cq.Workplane:
        points = self.mounting_points()
        if not points:
            return plate
        cutters = (
            cq.Workplane("XY")
            .pushPoints(points)
            .circle(self.hole_diameter / 2)
            .extrude(self.depth * 2)
        )
        return plate.cut(cutters)

    def create(self) -> cq.Workplane:
        return self.generate()

    def generate(self) -> cq.Workplane:
        raise NotImplementedError


@dataclass
class Base(PlatePart):
    def generate(self) -> cq.Workplane:
        return self._cut_mounting_holes(self._plate())


@dataclass
class WireSpaceModelU(PlatePart):
    depth: float = 6.35
    hole_diameter: float = 8
    cable_xoffset: float = 0
    usbc_depth: float = 1
    usbc_offset: float = 0.5
    usbc_buffer_width: float = 40
    usbc_buffer_height: float = 28.5
    cavity_offset: float = 20
    fastener_support_width: float = 20
    fastener_support_height: float = 20
    fastener_support_fillet: float = 2

    def generate(self) -> cq.Workplane:
        plate = self._cut_mounting_holes(self._plate())

        cavity = (
            cq.Workplane("XY")
            .rect(
                max(self.width - self.cavity_offset * 2, self.width * 0.5),
                max(self.height - self.cavity_offset * 2, self.height * 0.5),
            )
            .extrude(self.depth)
            .translate((0, 0, self.usbc_offset))
        )
        plate = plate.cut(cavity)

        usbc = (
            cq.Workplane("XY")
            .rect(self.usbc_buffer_width, self.usbc_buffer_height)
            .extrude(self.usbc_depth * 2)
            .translate((self.cable_xoffset, -self.height / 2, self.depth - self.usbc_depth))
        )
        return plate.cut(usbc)


@dataclass
class Switchplate(PlatePart):
    hole_diameter: float = 8
    switch_mount_dims: tuple[float, float] = (14, 14)

    def generate(self) -> cq.Workplane:
        plate = self._cut_mounting_holes(self._plate())
        points = list(self.layout.layout)
        if not points:
            return plate

        cutters = (
            cq.Workplane("XY")
            .pushPoints(points)
            .rect(*self.switch_mount_dims)
            .extrude(self.depth * 2)
        )
        return plate.cut(cutters)


@dataclass
class F1CapFaceplate(PlatePart):
    def generate(self) -> cq.Workplane:
        plate = self._cut_mounting_holes(self._plate())
        button_cut = self.layout.geom.extrude(self.depth * 2)
        return plate.cut(button_cut)


@dataclass
class KeycapFaceplate(PlatePart):
    keycap_dimensions: tuple[float, float] = (20.5, 20.5)
    keycap_fillet_radius: float = 0.1
    layout: Layout = field(default_factory=SquareCapLeverless)

    def generate(self) -> cq.Workplane:
        plate = self._cut_mounting_holes(self._plate())
        button_cut = self.layout.geom.extrude(self.depth * 2)
        return plate.cut(button_cut)


@dataclass
class Backplate(PlatePart):
    def generate(self) -> cq.Workplane:
        return self._cut_mounting_holes(self._plate())


@dataclass
class LayeredAssembly:
    parts: Sequence[PlatePart]

    def set(self, **kwargs) -> LayeredAssembly:
        return replace(self, parts=tuple(_replace_part(part, **kwargs) for part in self.parts))

    def generate(self) -> LayeredAssembly:
        return self


def _assembly(*parts: PlatePart) -> LayeredAssembly:
    return LayeredAssembly(parts=parts)


f1CapMako1 = _assembly(
    Base(),
    WireSpaceModelU(),
    Switchplate(),
    F1CapFaceplate(),
    Backplate(),
)

mako1 = _assembly(
    Base(),
    WireSpaceModelU(),
    Switchplate(),
    KeycapFaceplate(),
    Backplate(),
)
