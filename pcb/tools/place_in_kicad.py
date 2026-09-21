"""Run in KiCad: Tools > Scripting Console. Places the switches, the
bolt holes and the outline from makoreactor's layout."""
import pcbnew

MM = pcbnew.FromMM
board = pcbnew.GetBoard()

SWITCHES = [
    (-73.8500, 24.2500),
    (-100.0000, 36.0000),
    (-126.6500, 32.8000),
    (-153.3000, 16.5500),
    (73.8500, 46.2500),
    (100.0000, 58.0000),
    (126.6500, 54.8000),
    (153.3000, 38.5500),
    (73.8500, 24.2500),
    (100.0000, 36.0000),
    (126.6500, 32.8000),
    (153.3000, 16.5500),
    (-70.0000, -45.0000),
    (-51.5000, -57.7500),
    (70.0000, -45.0000),
    (51.5000, -57.7500),
    (70.0000, -19.5000),
    (51.5000, -32.2500),
    (88.5000, -32.2500),
    (0.0000, 18.0000),
]
BOLTS = [
    (-165.3000, -63.7000),
    (-165.3000, 63.7000),
    (165.3000, -63.7000),
    (165.3000, 63.7000),
    (-27.8000, -63.7000),
    (-27.8000, 63.7000),
    (27.8000, -63.7000),
    (27.8000, 63.7000),
]
BOLT_DIAMETER = 10
BOARD = (355.59999999999997, 152.39999999999998, 8)

origin = pcbnew.VECTOR2I(MM(BOARD[0] / 2), MM(BOARD[1] / 2))


def find(index):
    """Match on the address ato stamps into each footprint, so a
    reshuffled designator cannot silently move a button."""
    address = 'switches[%d]' % index
    for footprint in board.GetFootprints():
        try:
            if footprint.GetProperty('atopile_address') == address:
                return footprint
        except Exception:
            pass
    return board.FindFootprintByReference('SW%d' % (index + 1))

placed = 0
for index, (x, y) in enumerate(SWITCHES):
    footprint = find(index)
    if footprint is None:
        print('no footprint for switches[%d]' % index)
        continue
    footprint.SetPosition(pcbnew.VECTOR2I(MM(x), MM(-y)) + origin)
    placed += 1

# Bolt holes and the outline come in with the DXF this tool also
# writes -- File > Import > Graphics, onto Edge.Cuts.

pcbnew.Refresh()
print('placed %d of %d switches' % (placed, len(SWITCHES)))

