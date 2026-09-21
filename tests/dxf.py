"""A minimal DXF reader, just enough to compare exported plate outlines.

CadQuery writes plain ASCII DXF, so entities can be read straight out of the
group-code pairs without pulling in a full DXF library.
"""

import collections


def _entities(path):
    with open(path, errors="replace") as handle:
        lines = [line.strip() for line in handle]

    pairs = [(lines[i], lines[i + 1]) for i in range(0, len(lines) - 1, 2)]

    entities, current, inside = [], None, False
    for code, value in pairs:
        if code == "2" and value == "ENTITIES":
            inside = True
            continue
        if code == "0" and value == "ENDSEC":
            inside = False
        if not inside:
            continue
        if code == "0":
            if current:
                entities.append(current)
            current = {"type": value}
        elif current is not None:
            current.setdefault(code, []).append(value)
    if current:
        entities.append(current)
    return entities


class Drawing:
    """Summary of a 2-D DXF drawing, rounded so exports compare cleanly."""

    def __init__(self, path, ndigits=2):
        self.path = path
        self.entities = _entities(path)
        self.ndigits = ndigits

    def _round(self, value):
        return round(float(value), self.ndigits)

    @property
    def counts(self):
        return collections.Counter(e["type"] for e in self.entities)

    @property
    def circles(self):
        """``(x, y, radius)`` for every full circle, sorted."""
        return sorted(
            (self._round(e["10"][0]), self._round(e["20"][0]), self._round(e["40"][0]))
            for e in self.entities
            if e["type"] == "CIRCLE"
        )

    @property
    def arcs(self):
        """``(radius, x, y)`` for every arc, sorted."""
        return sorted(
            (self._round(e["40"][0]), self._round(e["10"][0]), self._round(e["20"][0]))
            for e in self.entities
            if e["type"] == "ARC"
        )

    @property
    def bounds(self):
        xs, ys = [], []
        for entity in self.entities:
            for code in ("10", "11"):
                xs += [float(v) for v in entity.get(code, [])]
            for code in ("20", "21"):
                ys += [float(v) for v in entity.get(code, [])]
        return (
            self._round(min(xs)), self._round(min(ys)),
            self._round(max(xs)), self._round(max(ys)),
        )

    @property
    def size(self):
        xmin, ymin, xmax, ymax = self.bounds
        return (self._round(xmax - xmin), self._round(ymax - ymin))
