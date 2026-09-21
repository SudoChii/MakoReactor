"""Command line entry point: generate a controller and export cuttable layers.

    python -m makoreactor --layout fgc --width 11.8 --height 5 -o build/
"""

import argparse
import pathlib
import sys

from affine import Affine
from cadquery import exporters

from . import layouts
from .parts.layered_leverless import (
    BrookAssembly,
    WireSpaceModelU,
    brookMako1,
    f1CapMako1,
    in2mm,
    mako1,
)
from .parts.sanwa_fgc import SanwaAssembly, sanwaFgc

STACKS = {"f1cap": f1CapMako1, "keycap": mako1, "brook": brookMako1, "sanwa": sanwaFgc}

LAYOUTS = {
    "fgc": layouts.FgcLeverless,
    "smash": layouts.CircleCapLeverless,
    "gccmx": layouts.Gccmx,
    "keycap": layouts.SquareCapLeverless,
    "hadoe": layouts.Mako1Hadoe,
    "widegc": layouts.WideGc,
    "sanwa": layouts.SanwaFgcLeverless,
}

#: Stacks whose own defaults are already sized for their buttons, so the
#: plate size and cluster shift are left alone unless asked for.
SELF_SIZED = {"sanwa", "brook"}

#: The layout each stack is designed around, used when --layout is not given.
#: The Brook stack cares: its board sits in a gap a particular layout leaves,
#: and its fit checks refuse to cut a stack where the two collide.
STACK_LAYOUT = {"f1cap": "fgc", "keycap": "fgc", "brook": "widegc", "sanwa": "sanwa"}


def build_parser():
    parser = argparse.ArgumentParser(prog="makoreactor", description=__doc__)
    parser.add_argument("-s", "--stack", choices=sorted(STACKS), default="f1cap",
                        help="plate stack to build (default: %(default)s)")
    parser.add_argument("-l", "--layout", choices=sorted(LAYOUTS), default=None,
                        help="button layout (default: whatever the stack is "
                             "designed around; see STACK_LAYOUT)")
    parser.add_argument("--width", type=float, default=None,
                        help="plate width, inches (default: the stack's own)")
    parser.add_argument("--height", type=float, default=None,
                        help="plate height, inches (default: the stack's own)")
    parser.add_argument("--hole-deltax", type=float, default=300.0,
                        help="mounting hole pitch in mm (default: %(default)s)")
    parser.add_argument("--n-modelu", type=int, default=2,
                        help="ModelU boards to make wire space for (default: %(default)s)")
    parser.add_argument("--shift-y", type=float, default=None,
                        help="shift the whole button cluster in mm (default: -13, "
                             "or 0 for stacks that centre their own layout)")
    parser.add_argument("-f", "--format", default="dxf", choices=["dxf", "svg", "step", "stl"],
                        help="export format (default: %(default)s)")
    parser.add_argument("-o", "--out", type=pathlib.Path, default=pathlib.Path("build"),
                        help="output directory (default: %(default)s)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    self_sized = args.stack in SELF_SIZED

    layout = LAYOUTS[args.layout or STACK_LAYOUT[args.stack]]()
    shift_y = args.shift_y if args.shift_y is not None else (0.0 if self_sized else -13.0)
    if shift_y:
        layout.layout_affine = Affine.translation(0, shift_y)

    settings = {"hole_deltax": args.hole_deltax, "n_modelu": args.n_modelu, "layout": layout}
    if args.width is not None:
        settings["width"] = in2mm(args.width)
    if args.height is not None:
        settings["height"] = in2mm(args.height)
    stack = STACKS[args.stack].set(**settings)

    # Assemblies that know their own fit constraints get to complain before
    # anything is written.
    if isinstance(stack, (SanwaAssembly, BrookAssembly)):
        results = stack.checks()
        for ok, text in results:
            print(f"  {'ok ' if ok else 'BAD'}: {text}")
        if any(not ok for ok, _ in results):
            print("\nfit checks failed; nothing written", file=sys.stderr)
            return 1

    args.out.mkdir(parents=True, exist_ok=True)

    for index, (part, solid) in enumerate(zip(stack, stack.generate())):
        # DXF and SVG are 2-D: export the top face outline, which is what a
        # laser or router actually needs.  A printed part has no useful flat
        # projection, so it falls back to a solid format.
        fmt = args.format
        if fmt in ("dxf", "svg") and not getattr(part, "flat", True):
            fmt = "step"

        # A part too big to print in one go is exported as the pieces you
        # actually put on the bed.
        name = type(part).__name__
        if hasattr(part, "halves"):
            pieces = list(zip(("left", "right"), part.halves(solid)))
            pieces = [(f"{name}_{side}", shape) for side, shape in pieces]
        else:
            pieces = [(name, solid)]

        depth = part.part_depth() if isinstance(part, WireSpaceModelU) else part.depth
        for piece_name, shape in pieces:
            path = args.out / f"{index}_{piece_name}.{fmt}"
            exporters.export(shape.edges(">Z") if fmt in ("dxf", "svg") else shape, str(path))
            print(f"{path}  ({depth:.2f}mm)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
