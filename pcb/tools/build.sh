#!/usr/bin/env bash
# Build the board and put everything where the layout says.
#
# `ato build` gives you the right parts and the right nets, but it does not
# know where anything goes -- it drops every footprint in a row at the origin.
# Placement is a second step, and it has to run after every build, including
# the ones the VS Code extension starts by itself when it notices a file
# change.  That is what this is for: one command, so the two cannot drift
# apart and leave you looking at a board with all 22 parts in a line.
#
#     tools/build.sh            # build, place, and check
#     tools/build.sh --export   # ...and write gerbers, STEP, DXF and a PDF
#
# None of the three tools it needs is on PATH, and two of them are easy to get
# wrong -- `python` finds miniforge's base environment, which has no cadquery
# in it -- so they are looked up rather than assumed.  Override any of them:
#
#     ATO=/path/to/ato PY=/path/to/python KICAD_CLI=/path/to/kicad-cli tools/build.sh
set -euo pipefail

cd "$(dirname "$0")/.."

die() { printf '%s\n' "$@" >&2; exit 1; }

# --- ato: installed by pip into its own env, because it needs Python 3.14 ---
find_ato() {
    for candidate in "${ATO:-}" "$HOME/miniforge3/envs/ato/bin/ato" \
                     "$(command -v ato 2>/dev/null || true)"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] && { echo "$candidate"; return; }
    done
    die "Cannot find the 'ato' command." \
        "  It lives in its own conda environment, because atopile needs Python 3.14:" \
        "      conda create -n ato -c conda-forge python=3.14 && conda activate ato" \
        "      pip install atopile" \
        "  Then re-run, or point at it: ATO=/path/to/ato tools/build.sh"
}

# --- python: must be the one that can import makoreactor, not base ---
find_python() {
    for candidate in "${PY:-}" "$HOME/miniforge3/envs/mako/bin/python" \
                     "$(command -v python 2>/dev/null || true)" \
                     "$(command -v python3 2>/dev/null || true)"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        # The coordinates come out of makoreactor, so this is the test that
        # matters -- not whether a python exists, but whether it is that one.
        if "$candidate" -c "import makoreactor" >/dev/null 2>&1; then
            echo "$candidate"; return
        fi
    done
    die "Cannot find a python that can import makoreactor." \
        "  The placement reads the layout out of it, so base python will not do:" \
        "      conda activate mako" \
        "  Or point at it: PY=~/miniforge3/envs/mako/bin/python tools/build.sh"
}

find_kicad() {
    for candidate in "${KICAD_CLI:-}" \
                     "$(command -v kicad-cli 2>/dev/null || true)" \
                     "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] && { echo "$candidate"; return; }
    done
    return 1
}

ATO=$(find_ato)
PY=$(find_python)
PCB=layout/default/default.kicad_pcb

echo "ato    $ATO"
echo "python $PY"

# The pour has to come off first: atopile segfaults on a board with zones.
# place_pcb.py puts it back at the end of this script.
[ -f "$PCB" ] && "$PY" tools/place_pcb.py --strip-zones

"$ATO" --non-interactive build
"$PY" tools/place.py --format json > tools/placement.json
"$PY" tools/place_pcb.py
"$PY" tools/route.py
"$PY" tools/place.py --format check

if [ "${1:-}" = "--export" ]; then
    KICAD_CLI=$(find_kicad) || die \
        "Cannot find kicad-cli, so there is nothing to export with." \
        "  On macOS it is inside the app bundle:" \
        "      /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli" \
        "  Point at it: KICAD_CLI=... tools/build.sh --export"
    echo "kicad  $KICAD_CLI"

    # Old plots are cleared out first.  They are named after the board file,
    # so a rename leaves the previous set sitting alongside the new one and
    # there is no telling which is which when it is time to order.
    rm -rf export/gerbers export/outline
    mkdir -p export/gerbers

    # Everything below plots from a *copy*, and that is the whole trick.
    #
    # A zone is only copper once it has been filled, and nothing fills it on
    # the way out: kicad-cli plots what is in the file, so an unfilled pour
    # plots as nothing at all -- the front gerber came out empty, with no
    # ground plane on it anywhere.  Filling needs --save-board, and saving
    # from KiCad rewrites the board in its own dialect: the net table goes,
    # pad nets become names without numbers, and atopile can no longer read
    # its own layout.  So the working file is never saved over.  The copy gets
    # filled, and the fab files come off that.
    # DRC runs on the working file, where the footprint libraries still
    # resolve; on the copy every footprint reports a missing library and the
    # report is 22 lines of noise about nothing.  --refill-zones so the pour
    # counts, and no --save-board, so nothing is written back.
    "$KICAD_CLI" pcb drc --refill-zones --format json -o export/drc.json "$PCB" || true

    FILLED=export/mako1_filled.kicad_pcb
    cp "$PCB" "$FILLED"
    # This one does save, which is what puts the copper in the pour.
    "$KICAD_CLI" pcb drc --refill-zones --save-board --format json \
        -o /dev/null "$FILLED" >/dev/null 2>&1 || true

    "$KICAD_CLI" pcb export gerbers --output export/gerbers "$FILLED" >/dev/null
    "$KICAD_CLI" pcb export drill --output export/gerbers/ "$FILLED" >/dev/null
    "$KICAD_CLI" pcb export dxf --output export/outline --layers Edge.Cuts \
        --output-units mm "$FILLED" >/dev/null
    "$KICAD_CLI" pcb export pdf --output export/mako1_top.pdf \
        --layers F.Cu,F.SilkS,Edge.Cuts "$FILLED" >/dev/null
    "$KICAD_CLI" pcb export step --output export/mako1_pcb.step --subst-models "$FILLED" >/dev/null
    echo "exported to export/"
fi
