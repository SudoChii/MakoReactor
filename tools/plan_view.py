"""Draw a layout the way you would inspect it: from above, labelled.

``show()`` in the notebook renders the solid, which is the right thing for
checking that parts fit together but close to useless for checking a *layout* --
the flat fallback looks straight down Z and every hole is the same grey circle.
This draws what you actually need to look at: which button is where, how big
its hole is, what the support plate opens up behind it, and where the screws
and the split land.

    python tools/plan_view.py                 # the FgcPlus stack, to plan.png
    python tools/plan_view.py --stack sanwaFgc --out fgc.png
"""

from __future__ import annotations

import argparse
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

import makoreactor as mr  # noqa: E402
from makoreactor import layouts as L  # noqa: E402

GROUP_COLOUR = {
    "left_homerow": "#2980b9",
    "right_homerow": "#111111",
    "left_thumb": "#c0392b",
    "right_thumb": "#c0392b",
    "misc": "#7f8c8d",
}


def draw(stack, out: pathlib.Path) -> pathlib.Path:
    top = stack.part(mr.SanwaTopPlate)
    support = stack.part(mr.SanwaSupportPlate)
    body = stack.part(mr.SanwaBody)
    layout = top.layout
    width, height = top.width, top.height

    figure, axes = plt.subplots(figsize=(width / 29, height / 29 + 1.2))
    axes.add_patch(Polygon(top.profile_points(), fc="#fbfbf9", ec="#333", lw=2, zorder=1))

    # What the support plate opens up: wide enough to merge, which is what
    # lets a finger get behind a button to pinch it out.
    for x, y, diameter in layout.buttons(support.button_clearance):
        axes.add_patch(Circle((x, y), diameter / 2, fc="#cfe3f7", ec="#4a90d9",
                              lw=1.0, zorder=2))

    index = 0
    for group in L.GROUPS:
        colour = GROUP_COLOUR[group]
        for point in layout.placed(group):
            x, y = layout.layout_affine * point
            diameter = layout.hole_diameter(group)
            axes.add_patch(Circle((x, y), (diameter + layout.bezel_clearance) / 2,
                                  fc="#e8e8e8", ec="#999", lw=0.8, zorder=3))
            axes.add_patch(Circle((x, y), diameter / 2, fc="#fff", ec=colour,
                                  lw=1.8, zorder=4))
            axes.text(x, y, str(index), ha="center", va="center", fontsize=7.5,
                      color=colour, zorder=5)
            index += 1

    for x, y in body.mounting_points():
        axes.add_patch(Circle((x, y), body.boss_diameter / 2, fc="#88888833",
                              ec="#888", lw=0.7, zorder=6))
        axes.add_patch(Circle((x, y), top.hole_diameter / 2, fc="#333", zorder=7))
    for x, y in body.board_screw_points():
        axes.add_patch(Circle((x, y), 6, fc="#2f6f4f33", ec="#2f6f4f", lw=1, zorder=6))
        axes.add_patch(Circle((x, y), top.hole_diameter / 2, fc="#2f6f4f", zorder=7))

    x0, y0, x1, y1 = body.board_holder_extent()
    axes.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec="#2f6f4f",
                             lw=1.2, ls="--", zorder=6))
    axes.axvline(body.split_x(), color="#e67e22", lw=1.4, ls="--", zorder=8)

    axes.set_title(
        "%s  |  %d buttons, %.0f x %.0fmm  |  white = hole, grey = bezel, "
        "blue = %.0fmm support opening"
        % (type(layout).__name__, len(layout), width, height,
           24 + support.button_clearance)
    )
    axes.set_xlim(-width / 2 - 8, width / 2 + 8)
    axes.set_ylim(-height / 2 - 8, height / 2 + 8)
    axes.set_aspect("equal")
    axes.grid(alpha=0.12)
    figure.tight_layout()
    figure.savefig(out, dpi=110)
    plt.close(figure)
    return out


def reach(stack) -> str:
    """The numbers a plan view makes you squint at.

    Thumb reach is the one worth watching: it is the distance a thumb travels
    from where the fingers rest, and it moves whenever either cluster does.
    """
    layout = stack.part(mr.SanwaTopPlate).layout
    lines = []
    for hand, group, thumb_group in (("left", "left_homerow", "left_thumb"),
                                     ("right", "right_homerow", "right_thumb")):
        fingers = layout.placed(group)
        thumbs = layout.placed(thumb_group)
        if not len(fingers) or not len(thumbs):
            continue
        # The index button: innermost of the home row, and the top row is home.
        top_row = max(point[1] for point in fingers)
        index = min((p for p in fingers if abs(p[1] - top_row) < 20),
                    key=lambda p: abs(p[0]))
        thumb = max(thumbs, key=lambda p: p[1])
        lines.append("  %-5s thumb reach %6.1fmm below the index button"
                     % (hand, index[1] - thumb[1]))
    lines.append("  Mako1's own MX/MY sit 69.2mm below theirs")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", default="sanwaFgcPlus",
                        choices=["sanwaFgcPlus", "sanwaFgc"])
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("plan.png"))
    args = parser.parse_args(argv)

    stack = getattr(mr, args.stack)
    print(draw(stack, args.out))
    print(reach(stack))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
