# Mako1 switch PCB

The board that goes where the switchplate goes: same outline, same bolt
pattern, 20 key switches on the layout's own centres, everything else hanging
underneath in the space `WireSpaceModelU` already opens up.

Written in [atopile](https://github.com/atopile/atopile) — the circuit is a
`.ato` file, the footprints and the placement are generated from the same
numbers the plates are cut from.

```bash
python tools/build_parts.py             # footprints and symbols -> parts/
ato build                               # netlist + footprints
python tools/place.py --format json > tools/placement.json
python tools/place_pcb.py               # put them where the layout says
python tools/place.py --format check    # does the layout still fit
python tools/place.py --format stack    # does the board still fit the stack
```

`ato build` gives you the right parts and the right nets, but it stacks them in
a row at the origin — the placement is the second half of the job, and
`place_pcb.py` is what does it: every switch on its layout centre, the Pico and
the Model UD flipped to the back, the outline and the eight bolt holes drawn on
Edge.Cuts. Run it after any `ato build`; it sets absolute positions, so running
it twice changes nothing.

### If the board looks like everything is in a line

That is a board that has been built but not placed, and it is what both the
atopile 3D view and the layout viewer in VS Code will show you, faithfully:
every footprint sitting at the origin 10mm apart, and no board outline — which
is also why `kicad-cli` starts warning `Board outline is malformed`. Both
symptoms are the one cause.

atopile owns the netlist and the footprints; nothing in the `.ato` file says
where a part goes, and 0.15.8 has no placement trait and no post-build hook to
hang one on. So a build that starts from a layout it cannot match writes the
default row, and the placement is gone.

The extension makes this easy to hit: it watches the project and rebuilds on
its own when a file changes. So run the two together rather than separately —

```bash
tools/build.sh            # ato build, then place, then check
tools/build.sh --export   # ...and write the fab files
```

It finds its own tools, because none of the three is on PATH and two of them
are easy to get wrong — plain `python` finds miniforge's *base* environment,
which has no cadquery in it, so the script tests each candidate by trying to
import `makoreactor` rather than trusting the name. Override any of them if
your paths differ:

```bash
ATO=/path/to/ato PY=/path/to/python KICAD_CLI=/path/to/kicad-cli tools/build.sh
```

— and if the viewer ever shows the row again, `python tools/place_pcb.py` puts
it back. It sets absolute positions, so it is safe to run at any time, and a
plain `ato build` afterwards keeps them.

### Why the placement does not go through pcbnew

It edits the `.kicad_pcb` as text rather than driving KiCad's Python, and that
is deliberate. **KiCad 10 rewrites a board it saves**: it drops the net table
and writes pad nets by name only — `(net "gnd")` where atopile expects
`(net 12 "gnd")`. atopile 0.15.8 cannot read that back, so one save from
pcbnew ends the round trip and the next `ato build` fails on its own layout
file. Editing the text in place keeps the file in the dialect both tools read.

Opening the board in KiCad is fine. Saving it there is a one-way door: after
that, re-run `ato build` from a clean `layout/` if you need the netlist
regenerated.

### Installing the CLI

atopile is **not on conda-forge** — it is PyPI only, and every release since
0.14.1006 needs **Python 3.14**, so it cannot go in the `mako` environment
(3.11). It wants its own:

```bash
conda create -n ato -c conda-forge python=3.14
conda activate ato
pip install atopile
```

Two things to know about the CLI. It prints `0.15.8 is the last CLI release and
is in maintenance mode only` on every run — atopile has moved to the editor
extension and app.atopile.io for 0.16+, so this project is pinned to a CLI that
will not get fixes. And `ato validate` is broken in 0.15.8
(`ImportError: cannot import name 'front_end'`); `ato build` works, which is
what matters here.

## Where the wiring comes from

None of it is invented. Two sources, both worth reading before changing
anything:

**[The Model UD wiring diagram](https://github.com/HTangl/Model-UD)** (in its
`Pictures/` folder) gives the breakout-to-Pico connections, and this board
makes all of them:

| Model UD | Pico | why |
| --- | --- | --- |
| GND | GND | — |
| VSYS | VSYS | through the breakout's own Schottky |
| 5V | VBUS | raw bus voltage |
| GCD | GP28 | GameCube detect — without it the board is USB only |
| D+ / D− | TP3 / TP2 | by wire; the Pico has no header pins for these |

The diagram also says *connect AGND to GND*, which this does. The pads are
named as the board silkscreens them — `GCD`, `D-`, `D+`, `GND`, `3V`, `VSYS`,
`5V`.

**[HayBox](https://github.com/JonnyHaystack/HayBox)** `config/pico/config.cpp`
gives the button pinout, and this board uses it verbatim — LF1-4 on GP2-5,
RF1-8 on GP26/21/19/17/27/22/20/18, LT1-2 on GP6-7, RT1-5 on
GP14/15/13/12/16, MB1 on GP0, and GP28 as `joybus_data`. HayBox names buttons
by position rather than by function, which is exactly how the layout groups
them, so the mapping is one-to-one and a board built to it runs stock firmware
with no config edit. `place.py --format check` fails if the pinout drifts from
that list.

## What is on it

| | |
| --- | --- |
| 20 key switches | Choc v1 hotswap or soldered; MX soldered |
| Raspberry Pi Pico | on the back, on headers or soldered flat |
| Model UD / BirdD | on the back, USB-C |
| bolt holes | the stack's own eight, nothing added |

Direct wired: one GPIO per switch, common ground, no matrix and no diodes.
GP2040-CE turns on the RP2040's internal pull-ups, so that is the entire
circuit — which is why the interesting part of this project is the footprint
and the placement rather than the schematic.

## The switch footprint

One footprint takes either standard, because the low profile switches this
board is built around are not the only ones people have in a drawer:

| | Kailh Choc v1 | Cherry MX (and MX-pinned low profile) |
| --- | --- | --- |
| hotswap socket | yes, CPG135001S30 on the back | no |
| soldered direct | yes | yes |

**MX cannot be hotswapped here.** Its socket wants 3mm holes at the MX pin
positions, and those overlap the Choc socket's — 2.67 and 2.77mm apart, when
each needs 3mm. One standard or the other gets the sockets, and since the
brief was low profile by default, Choc gets them.

Getting both standards into one footprint at all comes down to which holes
share a net. MX pin 2 lands 2.67mm from Choc pin 1, closer than any two
pieces of copper on different nets could be, so the poles are paired to put
those two on the *same* net, where they are allowed to overlap. What is left
between opposite poles is **0.173mm**, at the Choc pin 2 / MX pin 2 pair.
That is above a 2-layer fab's 0.127mm floor and below anything comfortable, so
`tools/build_parts.py` recomputes it on every run and refuses to write a
footprint that closes it further.

## Pinout

GP2040-CE's stock Pico mapping, so the board runs on stock firmware without a
config. Switch numbers are layout order — the same order `mako1.ato` declares
them and `tools/place.py` places them.

| SW | GPIO | GP2040-CE | | SW | GPIO | GP2040-CE |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GP4 | Right | | 11 | GP8 | R2 |
| 2 | GP3 | Down | | 12 | GP20 | A1 |
| 3 | GP5 | Left | | 13 | GP2 | Up |
| 4 | GP13 | L1 | | 14 | GP21 | A2 |
| 5 | GP10 | B3 | | 15 | GP19 | R3 |
| 6 | GP11 | B4 | | 16 | GP18 | L3 |
| 7 | GP12 | R1 | | 17 | GP16 | S1 |
| 8 | GP9 | L2 | | 18 | GP14 | spare |
| 9 | GP6 | B1 | | 19 | GP15 | spare |
| 10 | GP7 | B2 | | 20 | GP17 | S2 / start |

GP14 and GP15 are the two c-stick positions this layout has and GP2040-CE's
default mapping does not; assign them in the web configurator.

## USB needs two wires

The Pico's D+ and D- do not come out on its 40-pin header — they are only on
the TP2/TP3 pads underneath it. So the Model UD's pair stops at a labelled
link beside the Pico footprint, and you run two short wires to those pads.
Every DIY Pico controller does this; there is no way to do it in copper alone
short of reflowing the Pico flat and trusting its test pads to land, which is
not a thing to ask of a hand-built board.

Power does not need wires: the Model UD's VSYS pin is VBUS through its own
Schottky, which is exactly what the Pico's VSYS wants, so it is a track.

## Fitting the stack

The switchplate it replaces is 3.175mm; a PCB is 1.6mm. **The stack loses
1.575mm** unless you make it up — either 1.6mm of spacer under the faceplate,
or order the board at 3.2mm, or let the keycaps sit that much lower, which
with low profile switches may be what you want anyway. Nothing in the layered
parts changes; `Switchplate` simply is not cut.

`tools/place.py` reports the clearances that matter on the current layout:

```
closest two switch footprints: +2.95mm
closest switch to a bolt hole: +9.91mm
closest switch to the board edge: +8.67mm
```

## What is checked, and what is not

**It builds.** `ato build` runs clean through every stage — instance graph,
electrical design, PCB update, post-PCB checks and all the report targets — and
writes `layout/default/default.kicad_pcb` with 22 footprints on it: 20
`MakoKeySwitch`, one Pico, one Model UD, designated SW1-SW20, U1 and J1.

The netlist has been read back out of that PCB and checked against the source:
all 20 switch A poles land on the GPIO `mako1.ato` names them to, all 20 B
poles share one net, and the Pico and Model UD agree on `gnd` and `vsys`. Nets
are named by function — `sw_right`, `sw_b1`, `usb_dp` — so the board reads
without cross-referencing.

Four things the first build turned up, in case they help elsewhere: trait
arguments cannot span lines; footprints must be the modern `(footprint ...)`
s-expression, not the legacy `(module ...)`; designators are only handed to
parts carrying `has_part_picked`, so a custom part needs it even though nothing
is being picked; and `override_net_name` only takes on a concrete package pin
(`pico.package.GND`), not on a locally declared interface, where the stdlib's
own `hv`/`lv` suggestions win.

**DRC is clean.** `kicad-cli pcb drc` reports 0 violations on the placed board
(KiCad 10.0.5). The 105 unconnected items it also reports are the nets: there
are no traces yet — `ato build` and `place_pcb.py` give you parts, nets and
placement, and routing is still yours to do.

Three things DRC caught that the earlier hand checks had missed, all now fixed:

- The switch footprint was drawn at the **19.05mm key pitch instead of the
  15.6mm switch body**, so on a layout whose thumb cluster sits at 18.5mm every
  one of those footprints overlapped its neighbour.
- `fits()` measured the straight-line distance between switch centres, which is
  the wrong measure for two axis-aligned squares — it read +2.95mm on a pair
  that overlapped by a millimetre. It measures the box gap now.
- The MX pin pad at 1.9mm came within 0.173mm of the Choc socket pad beside it,
  under the 0.2mm a 2-layer fab holds. At 1.8mm it clears by 0.223mm, with
  0.15mm of annular ring left.

The symbols are minimal hand-rolled `.kicad_sym` files, enough to carry pin
names.

## Exports

```bash
kicad-cli pcb export gerbers --output export/gerbers layout/default/default.kicad_pcb
kicad-cli pcb export drill   --output export/gerbers/ layout/default/default.kicad_pcb
kicad-cli pcb export dxf     --output export/outline --layers Edge.Cuts --output-units mm ...
kicad-cli pcb export step    --output export/mako1_pcb.step ...
```

The DXF and the STEP are the ones that answer *does it fit*, and they have been
checked against the plate rather than eyeballed: the exported outline is
**355.60 x 152.40mm** against the switchplate's 355.60 x 152.40, and its eight
bolt holes land on the plate's own pattern at 10mm. The STEP imports into
cadquery beside the rest of the stack.

Note `--output-units mm`: kicad-cli writes DXF in inches by default, which is
how an outline that is exactly right shows up as "14.00 x 6.00".

### The one thing that does not fit

`python tools/place.py --format stack` spells it out: the PCB is **1.6mm where
the switchplate was 3.175mm**, so there is 1.575mm to make up in the stack.

1.6mm is the right number, not a compromise — an MX or Choc switch clips into a
1.5mm plate, and that is what a board of this thickness gives it. The plate it
replaces was 1/8in because it was acrylic and had to be stiff on its own. So
either shim the difference, or set `Switchplate(depth=1.6)` and let the stack
come out 1.575mm shorter.

Everything that hangs underneath fits the 12.7mm wire space: the Pico soldered
flat is 2.4mm, on headers 11.0mm, the Model UD 5.0mm, and Choc sockets 1.85mm.
The Pico on headers is what wants `n_modelu=2` rather than 1.

The footprint geometry is checked, and against real sources: Cherry MX and
Kailh Choc drawings, cross-referenced with
[daprice/keyswitches.pretty](https://github.com/daprice/keyswitches.pretty)
(CC BY-SA 4.0), and the Model UD dimensions measured out of the Model BirdD
KiCad files in [HTangl/Model-UD](https://github.com/HTangl/Model-UD). Before
ordering, diff `parts/MakoKeySwitch/MakoKeySwitch.kicad_mod` against a
footprint from a library you trust — 0.173mm is not the place to find out a
number was off.
