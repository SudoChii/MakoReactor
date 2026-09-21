# Mako Reactor

CAD-as-code for layered leverless ("hitbox" style) fight controllers.

Describe where the buttons go, and Mako Reactor gives you back a stack of flat
plates you can send to a laser cutter, router, or 3D printer.

```python
import makoreactor as mr
from affine import Affine
from cadquery import exporters

layout = mr.FgcLeverless()
layout.layout_affine = Affine.translation(0, -13)

stack = mr.f1CapMako1.set(
    width=mr.in2mm(11.8),
    height=mr.in2mm(5),
    hole_deltax=300,
    layout=layout,
)

for i, plate in enumerate(stack.generate()):
    exporters.export(plate.edges(">Z"), f"layer{i}.dxf")
```

Or from a shell:

```bash
python -m makoreactor --layout fgc --width 11.8 --height 5 -o build/
```

## Install

Everything is available from conda-forge, so a single environment file covers it:

```bash
# replace mamba with conda if you don't have mamba
mamba env create -f environment.yml
mamba activate mako

pip install -e .
```

If you'd rather use pip alone, `pip install -e .` pulls `cadquery`, `numpy`, and
`affine` from PyPI; CadQuery ships the OpenCascade binaries as wheels.

Check it works:

```bash
pytest
```

## How it fits together

### Layouts (`makoreactor/layouts.py`)

A `Layout` holds button centres grouped by hand and function — `left_homerow`,
`right_homerow`, `left_thumb`, `right_thumb`, `misc` — and one affine per group
placing it on the plate. `layout_affine` shifts the whole cluster at once.

| layout | buttons | notes |
| --- | --- | --- |
| `CircleCapLeverless` | 20 | smash layout, Frame 1 circular caps |
| `Gccmx` | 22 | as above plus home/share, mimics Crane's GCCMX |
| `SquareCapLeverless` | 20 | smash layout, square MX keycaps |
| `Mako1Hadoe` | 20 | as above, right-hand eight dropped onto the home row |
| `WideGc` | 18 | as `Gccmx`, two thumb buttons a hand, no left pinky |
| `FgcLeverless` | 15 | traditional fighting-game layout, one thumb button |
| `SanwaFgcLeverless` | 15 | as above, spread out for 24/30mm Sanwa buttons |
| `FgcPlus` | 16 | as above on the smash spacing, pinky and two thumbs a hand, all 24mm |

The eight action buttons sit in two rows 22mm apart. In the smash layouts the
*bottom* row lines up with the four directionals, so the fingers rest low and
reach up; `Mako1Hadoe` drops the whole cluster by that one row pitch so the
*top* row lands on the home row instead.

`WideGc` keeps the smash spacing and the right hand's eight, and changes the
other three groups. The stock thumbs are lopsided — two buttons on the left, a
five-button c-stick on the right — so it cuts the right cluster back to its
bottom two, the same pair the left thumb already has, and both thumbs end up
with the same reach. The centre is Crane's, inherited from `Gccmx`: a row of
three on a 20mm pitch where the stock layout has one button. The left hand
loses its pinky — the outermost of its four, the same button `FgcLeverless`
drops — leaving three directionals. Eighteen buttons.

Dropping the pinky leaves the cluster 13mm right of the plate centre, since
nothing came off the right hand. Shift it back with
`layout.layout_affine = Affine.translation(-13.3, 0)` if that matters for the
plate you are cutting.

`layout.layout` is the flat list of centres in plate coordinates;
`layout.geom` is the same thing as cap outlines ready to cut.

### Parts (`makoreactor/parts/layered_leverless.py`)

Each part is a rounded rectangle with mounting holes, plus whatever it cuts:

| part | cuts |
| --- | --- |
| `Base` | nothing — solid bottom |
| `WireSpaceModelU` | interior frame for wiring, plus the USB-C breakout pocket |
| `Switchplate` | 14x14 switch mounts on every button centre |
| `F1CapFaceplate` | circular cap openings |
| `KeycapFaceplate` | square keycap openings |
| `Backplate` | cap openings, cosmetic top |
| `BrookWireSpace` | as `WireSpaceModelU`, deep enough to hang a Brook board in |
| `BrookSwitchplate` | as `Switchplate`, plus four board screws and a relief window |

Mounting holes are nested rectangles inset from the edge by `hole_offset`, each
one `hole_deltax` narrower than the last, until another would not fit. A 13.5"
plate at the default 275mm pitch gets eight holes; an 11.8" plate at 300mm gets
the four corners.

`WireSpaceModelU` carries the USB-C opening. Going inwards from the plate edge:
a `usbc_slot_width` slot the connector pokes through, then a
`usbc_pocket_width` x `usbc_pocket_depth` pocket that the small breakout PCB
sits in, with a `usbc_relief_radius` semicircle either side of it — tangent to
the pocket walls and centred on its top edge — so the board can be seated and
levered back out. Below that, `usbc_throat_width` runs the wires down into the
cavity between the two arms of the boss.

#### Housing a Brook board (`brookMako1`)

`brookMako1` is the same five layers with two of them swapped, for a build that
carries a Brook Gen-5X/UFB rather than ModelU boards alone. The board hangs
face-up under the switchplate on standoffs, and everything else follows from
that:

```python
stack = mr.brookMako1                  # WideGc layout, 14x6", two 1/4" spacers
for ok, why in stack.checks():
    print("ok " if ok else "BAD", why)
```

`BrookWireSpace` needs no new cutout — the layer is already an open frame — so
what it adds is *depth*. Plates come from sheet, so depth only arrives in whole
thicknesses of stock: `spacers()` rounds the board up to a whole number of 1/4"
layers and `part_depth()` never returns less, whatever `n_modelu` says. The
board then sits as low as it goes, and `standoff_length()` is the rest of the
depth — the standoffs to actually buy. At the defaults that is two spacers,
12.70mm, and 8.10mm standoffs.

Whatever the components reach above that has to go somewhere, which is
`BrookSwitchplate`. It cuts four screw holes on the board's mounting pattern
and a window over the middle of the board — the PCB outline pulled in by
`board_rim`, so a rim of material is left all the way round carrying those four
screws. The window goes clean through, because these plates are cut flat and
there is no such thing as a pocket here. At the defaults the components stand
2.90mm proud of the switchplate's underside and the plate is 3.175mm thick, so
the faceplate closes over them untouched. Three spacers instead of two would
swallow the board whole and the window could come off (`board_relief=False`).

`checks()` measures all of that, plus the things that depend on where the board
sits: clearance to the nearest switch mount, to the corner screws, to the cavity
wall and the corner pads, and that each of the four screws lands on material
rather than in a switch mount. `check()` raises instead, and the CLI runs it
before writing anything:

```bash
python -m makoreactor --stack brook -o build/
```

Swap the layout and the checks are what notice. `--layout fgc` puts the FGC
layout's action buttons straight through the board, and the run stops with
`BAD: board clears the nearest switch mount by -24.5mm` rather than cutting it.

**Two numbers here are assumptions, not datasheet.** Brook publishes neither the
mounting hole pattern nor a height, so `BrookBoard` assumes holes 3.5mm in from
each corner — an 89.01 x 38.01mm pattern, the same assumption
`SanwaBody.board_hole_inset` already made, with a test pinning the two together
— and an 11mm tallest component. Measure your board before cutting; both are
fields, and `component_height` is the one that decides whether the faceplate
stays closed.

### Sanwa parts (`makoreactor/parts/sanwa_fgc.py`)

The same idea built out of arcade parts instead of mechanical switches. Snap-in
buttons need a panel 2–3.9mm thick to grip, but a 320mm plate that thin flexes,
and a rear panel, a board mount and screw bosses are not flat — so the stack
splits into three cut plates and one printed body:

| part | is | carries |
| --- | --- | --- |
| `SanwaTopPlate` | 3mm, cut | the button holes, 24mm and 30mm |
| `SanwaSupportPlate` | 6mm, cut | the same holes 4mm wider; stiffens the top plate |
| `SanwaBody` | 36mm, printed in two | walls, rear panel, board holder, skirt, screw bosses |
| `SanwaBottomPlate` | 3mm, cut | closes the bottom |

Two stacks ship: `sanwaFgc` on the FGC layout (320 x 200mm) and `sanwaFgcPlus`
on `FgcPlus` (460 x 215mm), which puts the hands 200mm apart as the smash
layouts do and rests both of them on the same row.

`FgcPlus` is arranged around the **top** row of the right-hand eight being the
home row, where the fingers rest:

* the left hand gets four buttons — the mirror of the right hand's second row,
  pinky included — carried up one `row_pitch` so it lands level with the right
  hand's *top* row. Both hands rest at the same height.
* the thumbs sit exactly where the smash layouts put MX and MY — just inboard
  of the index finger and well below it — and stay there when the hands go up,
  so the reach is longer here than on those layouts: 87mm below the index
  button against Mako1's 69mm.
* the three menu buttons are off the face — they are on the back panel, and
  hanging them off one corner stopped the cluster centring. Put them back with
  `layout.misc_coords = FgcLeverless.misc_coords`.

The board sits under the right palm, outboard of the thumb cluster. That corner
is what sets the width: with the thumbs at MX/MY they take the inboard half of
it, and the cluster is centred, so the room has to come from both sides.

#### How it goes together

Nothing threads into plastic and nothing is glued. The printed body takes brass
**M3 heat-set inserts** — a 4.2mm hole 6mm deep, the standard seat for a
4.6 × 5.7mm insert — pressed in with a soldering iron before anything else
happens. Every screw is then an M3 machine screw into brass, and every insert
goes in from the face its screw comes from, so all of them are reachable on a
bare printed half.

`fasteners()` prints the schedule for whatever the stack is currently set to:

```
22 x M3 heat-set inserts, 4.2mm hole x 6mm deep
14 x M3 x 14 screws, down through both top plates into the body
 8 x M3 x 8 screws, up through the bottom plate
 4 x M3 x 8 self-tapping screws, up into the board standoffs
 2 x 4mm dowels x 10mm, locating the printed halves
```

Then, in order: dowel the two halves together, press the rear buttons and the
jack into the back panel, screw the board up into its standoffs from
underneath, snap the face buttons into the top plate and wire them, lay the
support plate on the body and the top plate on that, and run the long screws
down through both into the rim. The bottom plate goes on last, from below, and
is the only thing to take off to get at the board again.

#### Where the screws go

The rim pattern follows the chamfered outline in: **one screw per chamfer**
rather than one either side of it, then as many along each straight edge as it
takes to keep the spacing under `screw_pitch`. The top two plates pick up two
more over the board holder, so the middle of the span is fastened as well as
the edge.

The bottom plate does not repeat all of that. Nothing pushes on it and it
carries no buttons, so it takes a **subset** of the rim — the four corners plus
enough of the rest to keep its own spacing under `bottom_screw_pitch`. Every
screw it skips is a heat-set insert saved too. Between that and the single
corner screws, a `sanwaFgc` went from 32 fasteners to 22.

**The outline** is a rectangle with the corners chamfered off rather than
rounded, and both ends of every chamfer rounded — `corner_chamfer` and
`corner_fillet`. The cavity follows it in, so the wall stays an even thickness
the whole way round.

**The board hangs from the top of the cavity**, not off the floor: an 8mm slab
under the lid, the Brook on standoffs below it, and that same slab taking the
two middle screws. Pulling the bottom plate gets you at the board without
touching the button plates.

**The skirt** is a flange turned inwards round the bottom of the walls,
`skirt_width` deep into the cavity. The body is open underneath, which leaves
the printed halves floppy and the bottom plate spanning unsupported; the skirt
ties the walls together, carries the plate all the way round, and gives the
print a wide flat face. Its opening repeats the outline's treatment at a larger
scale — a chamfered rectangle with the chamfers rounded — and has to stay big
enough to pass the board through, since the board goes in from underneath.

**The back wall** puts the USB-C jack on the centreline in the Neutrik D-series
footprint (24mm bore, two M3 screws diagonally opposite it), with 24mm OBSF-24
buttons divided evenly either side — two and two by default,
`rear_button_count=6` for three a side, and the pitch closes up on its own so
the outermost button still lands on the straight part of the wall. Nothing back
there is bigger than a 24mm button; the 30mm one is the face thumb button, and
it is a 36mm wall. Neither a snap-in button nor the jack will fit that wall, so
it is relieved from the inside to `rear_panel_thickness` around each of them.

Each rear button gets a **release slot** either side of it, `tab_slot_width` x
`tab_slot_height`, running right up to the hole. A snap-in button's tabs are
behind the panel they grip, and once the case is shut there is no other way to
reach them; with the slots you can pinch the tabs through the wall and push the
button back out. The bezel covers most of each slot. They widen what a rear
button asks of the wall, so the screw and split placement works around them
too.

Where the screws can go along that edge is decided by what is mounted in it: a
button's body reaches 24.5mm past the wall, so a boss behind one would be inside
it. `rear_screw_points()` drops one into each bay between components wide enough
to take it, and leaves the ends to the side edges.

**The body prints in two pieces.** It does not fit a bed whole, so `halves()`
cuts it down `split_x()` — not down the middle, where the jack is, but through
the clear bay beside it. That position is derived from the rear panel rather
than fixed, so moving the buttons moves the split instead of stranding it in
one of them; `split_offset` pins it if you want. The halves locate on dowels
through the front and back walls and are clamped by the plates that screw into
both. `sanwaFgc` comes off a 220 x 220mm bed; `sanwaFgcPlus` is bigger and
wants 250 x 250.

Almost every dimension here is pinned by another one, so the assembly states
those constraints as checks rather than leaving them in a comment:

```python
for ok, why in mr.sanwaFgcPlus.checks():
    print("ok " if ok else "BAD", why)
```

`check()` raises instead, and both the CLI and the tests run it. It is what
caught the failures this design walked into: a rear button whose body passes
through a screw boss, a jack tucked under the corner where the misc buttons hang
down into the same space, a plate too shallow to keep rear button bodies clear
of the row in front of them — which is why it is 200mm deep rather than the
170mm the button layout alone needs — four corner screws left hanging in the air
once the corners were chamfered, and a board holder wide enough to reach a wall
only by cutting through the thumb cluster on the way.

```bash
python -m makoreactor --stack sanwa -o build/   # plates as DXF, body halves as STEP
```

### Sharing parameters

`LayeredAssembly.set(**kwargs)` pushes shared parameters into every layer that
accepts them and returns a new assembly, so stacks are cheap to fork:

```python
wide = mr.f1CapMako1.set(width=mr.in2mm(13.5), hole_deltax=275)
```

`generate()` returns the plates in stack order; `assemble()` returns a CadQuery
`Assembly` with them stacked along Z.

## Reference exports

`notebooks/mako1_fgc/layer{0..4}.dxf` were cut from real material and are
treated as the specification. `tests/test_reference_export.py` regenerates them
and compares outlines, mounting holes, button openings, and fillet arcs.

The parts module was never committed to this repo — it was reconstructed from
those exports, the notebook that produced them, and the earlier
`makogen/parts.py` in the git history. All five layers now regenerate exactly:
every entity count, every hole, and every arc matches to the hundredth of a
millimetre.

## Notebook and rendering

`notebooks/demo.ipynb` walks through layouts, building a stack, rendering it,
exporting DXFs, and a Pi Pico holder.

```bash
jupyter lab notebooks/demo.ipynb
```

Its `show()` helper prefers [jupyter-cadquery][jcq] for interactive OCP
rendering and falls back to a flat inline SVG when the viewer is missing or no
Jupyter server is reachable — so the notebook still runs headless under
nbconvert or nbclient.

[jcq]: https://github.com/bernhard-42/jupyter-cadquery

To get the 3-D viewer, use the environment that pins a matching OCP:

```bash
mamba env create -f environment-viewer.yml
mamba activate mako-viewer
pip install -e ".[viewer]"
```

jupyter-cadquery 4.0.2 targets OCP 7.8, which is what CadQuery 2.7 pins, so that
environment holds CadQuery one minor version back and resolves cleanly. If you
are already on CadQuery 2.8 (OCP 7.9), the viewer works there too, but you need
newer tessellation than jupyter-cadquery asks for — `pip` will report the pin
conflict, and it is safe to ignore:

```bash
pip install jupyter-cadquery
pip install --upgrade ocp-tessellate ocp-vscode
```

`LayeredAssembly.assemble()` is built for this: it stacks the layers along Z and
colours them so they can be told apart. Pass `explode=True` to load the viewer's
explode tool, then drag the animation slider under the render to pull the plates
apart and check that cutouts line up between layers.

```python
show(stack.assemble(), explode=True)
```

The explode distance is fixed at 2.5x by the viewer itself — three-cad-viewer's
`explode(duration=2, speed=1, scale=2.5)` is called with no arguments, and
jupyter-cadquery's `explode` is only a boolean that switches the tool on. If you
need the plates further apart, `assemble(gap=...)` spaces them in the model
instead, which also works without the viewer.

To send renders to a docked side panel instead of the cell output, call
`open_viewer("Mako", anchor="right")` once.
