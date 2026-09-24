"""Zeichnet die Szene der Baumseite als statische SVG-Dateien.

Alles hier ist Geometrie ohne Daten: Baum, Hügel, Wolken, Wiese, Zäune, Bank
und Büsche hängen nicht vom Paar ab, das die Seite ansieht. Deshalb wird die
Szene einmal gerechnet und als Dateien unter ``static/img/tree/`` committet.
Der Browser holt sie über ``static_url`` mit Content-Hash und cacht sie ein
Jahr lang, die HTML-Seite selbst bleibt klein. Zur Laufzeit rechnet nichts,
weder auf dem Pi noch auf Vercel.

Der Zufall ist geseedet: Jeder Lauf zeichnet exakt dieselbe Szene, ein
erneuter Lauf ohne Codeänderung erzeugt keinen Diff.

Der Baum liegt im selben Koordinatenfeld wie der alte (viewBox
``-20 -10 580 500``) und seine Krone deckt die Ellipsen ab, an die
``clampToCrown`` in ``templates/tree.html`` gezogene Erinnerungen bindet.
Gespeicherte Positionen (``tree_pos_top``/``tree_pos_left``, Prozent des
Baum-Containers) bleiben so gültig.

    python scripts/build_tree_scene.py
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

OUT = Path(__file__).resolve().parent.parent / "static" / "img" / "tree"

Punkt = tuple[float, float]
Knoten = tuple[float, float, float]


# ── Grundlagen ──────────────────────────────────────────────────────────────


def zufall(seed: int) -> Callable[[], float]:
    """Kleiner, geseedeter Zufallsgenerator (mulberry32), plattformunabhängig."""
    state = seed & 0xFFFFFFFF

    def imul(a: int, b: int) -> int:
        return (a * b) & 0xFFFFFFFF

    def rand() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = imul(state ^ (state >> 15), 1 | state)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rand


def f(n: float) -> str:
    """Zahl mit höchstens einer Nachkommastelle, ohne überflüssige Nullen."""
    s = f"{round(n, 1):.1f}"
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def glatt(p: list[Punkt]) -> str:
    """Catmull-Rom durch alle Punkte, als kubische Bézier-Segmente (ohne M)."""
    d = ""
    for i in range(len(p) - 1):
        a = p[i - 1] if i > 0 else p[i]
        b, c = p[i], p[i + 1]
        e = p[i + 2] if i + 2 < len(p) else c
        c1 = (b[0] + (c[0] - a[0]) / 6, b[1] + (c[1] - a[1]) / 6)
        c2 = (c[0] - (e[0] - b[0]) / 6, c[1] - (e[1] - b[1]) / 6)
        d += f"C{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(c[0])} {f(c[1])}"
    return d


def geschlossen(p: list[Punkt]) -> str:
    """Geschlossene, glatte Form durch alle Punkte."""
    q = p[-1:] + p + p[:2]
    d = f"M{f(p[0][0])} {f(p[0][1])}"
    for i in range(1, len(p) + 1):
        a, b, c, e = q[i - 1], q[i], q[i + 1], q[i + 2]
        c1 = (b[0] + (c[0] - a[0]) / 6, b[1] + (c[1] - a[1]) / 6)
        c2 = (c[0] - (e[0] - b[0]) / 6, c[1] - (e[1] - b[1]) / 6)
        d += f"C{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(c[0])} {f(c[1])}"
    return d + "Z"


def ast(knoten: list[Knoten]) -> str:
    """Ein Ast als gefüllte, sich verjüngende Form mit runder Spitze."""
    links: list[Punkt] = []
    rechts: list[Punkt] = []
    n = len(knoten)
    for i, (x, y, w) in enumerate(knoten):
        vor = knoten[max(0, i - 1)]
        nach = knoten[min(n - 1, i + 1)]
        tx, ty = nach[0] - vor[0], nach[1] - vor[1]
        ln = math.hypot(tx, ty) or 1
        nx, ny = -ty / ln, tx / ln
        links.append((x + nx * w / 2, y + ny * w / 2))
        rechts.append((x - nx * w / 2, y - ny * w / 2))
    r = max(knoten[-1][2] / 2, 0.6)
    zurueck = rechts[::-1]
    return (
        f"M{f(links[0][0])} {f(links[0][1])}"
        + glatt(links)
        + f"A{f(r)} {f(r)} 0 0 1 {f(zurueck[0][0])} {f(zurueck[0][1])}"
        + glatt(zurueck)
        + "Z"
    )


def versetzt(knoten: list[Knoten], dx: float, faktor: float) -> list[Knoten]:
    """Derselbe Ast seitlich versetzt und schmaler: Licht- oder Schattenkante."""
    return [(x + dx * (w / knoten[0][2]), y, w * faktor) for x, y, w in knoten]


def blatt_pfad(x: float, y: float, winkel: float, laenge: float, breite: float) -> str:
    """Ein Blatt als Unterpfad in ganzen Einheiten: Spitze, Bogen, zurück."""
    ux, uy = math.cos(winkel), math.sin(winkel)
    lx, ly = round(ux * laenge), round(uy * laenge)
    cx, cy = round(lx / 2 - uy * breite), round(ly / 2 + ux * breite)

    def z(n: int) -> str:
        return f"{n}" if n < 0 else f" {n}"

    return (
        f"M{round(x - lx / 2)}{z(round(y - ly / 2))}"
        f"q{cx}{z(cy)}{z(lx)}{z(ly)}"
        f"q{-cx}{z(-cy)}{z(-lx)}{z(-ly)}"
    )


def svg(viewbox: str, body: str, *, extra: str = "", style: str = "") -> str:
    style_tag = f"<style>{style}</style>" if style else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}"{extra}>'
        f"{style_tag}{body}</svg>\n"
    )


def schreibe(name: str, inhalt: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(inhalt, encoding="utf-8")
    print(f"  {name:<22} {len(inhalt.encode()) / 1024:6.1f} KB")


# Bewegung nur, wenn niemand sie abgeschaltet hat. Gilt in jeder Datei.
RUHE = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


# ── Laub ────────────────────────────────────────────────────────────────────

Ellipse = tuple[float, float, float, float]


def in_ellipsen(ell: list[Ellipse], x: float, y: float, rand: float = 0) -> bool:
    return any(
        ((x - cx) / (rx - rand)) ** 2 + ((y - cy) / (ry - rand)) ** 2 <= 1
        for cx, cy, rx, ry in ell
        if rx - rand > 0 and ry - rand > 0
    )


def laub(
    rand: Callable[[], float],
    ell: list[Ellipse],
    *,
    mitte: Punkt,
    rand_blaetter: int,
    gesamt: int,
    groesse: float,
    licht: Callable[[float, float], float],
    toene: int,
    innen_abstand: float = 13,
) -> list[list[str]]:
    """Blätter in einer Vereinigung von Ellipsen, nach Ton gebündelt.

    Am Rand dicht und nach außen gerichtet: Er macht den Umriss. Innen in
    lockeren Büscheln, damit die Fläche Struktur bekommt und der Grund
    durchscheint. ``licht`` liefert 0 (Schatten) bis 1 (Licht) je Punkt.
    """
    xs = [cx - rx for cx, _, rx, _ in ell] + [cx + rx for cx, _, rx, _ in ell]
    ys = [cy - ry for _, cy, _, ry in ell] + [cy + ry for _, cy, _, ry in ell]
    x0, x1, y0, y1 = min(xs) - 8, max(xs) + 8, min(ys) - 8, max(ys) + 8
    gruppen: list[list[str]] = [[] for _ in range(toene)]

    def setze(x: float, y: float, winkel: float) -> None:
        l_wert = licht(x, y) + (rand() - 0.5) * 0.35
        ton = max(0, min(toene - 1, round(l_wert * (toene - 1))))
        laenge = groesse * (0.8 + rand() * 0.45)
        breite = laenge * (0.42 + rand() * 0.16)
        gruppen[ton].append(blatt_pfad(x, y, winkel, laenge, breite))

    n = 0
    for _ in range(80000):
        if n >= rand_blaetter:
            break
        x, y = x0 + rand() * (x1 - x0), y0 + rand() * (y1 - y0)
        if not in_ellipsen(ell, x, y, -groesse * 0.45) or in_ellipsen(ell, x, y, innen_abstand):
            continue
        aussen = math.atan2(y - mitte[1], x - mitte[0])
        setze(x, y, aussen + (rand() - 0.5) * 1.7)
        n += 1
    for _ in range(80000):
        if n >= gesamt:
            break
        bx, by = x0 + rand() * (x1 - x0), y0 + rand() * (y1 - y0)
        if not in_ellipsen(ell, bx, by, groesse * 0.7):
            continue
        for _ in range(5):
            w = rand() * math.pi * 2
            d = math.sqrt(rand()) * groesse
            setze(bx + math.cos(w) * d, by + math.sin(w) * d, rand() * math.pi * 2)
            n += 1
    return gruppen


def laub_svg(gruppen: list[list[str]], farben: list[str], klasse: str = "") -> str:
    k = f' class="{klasse}"' if klasse else ""
    return "".join(
        f'<path{k} fill="{farben[i]}" d="{"".join(g)}"/>' for i, g in enumerate(gruppen) if g
    )


# ── Der Baum ────────────────────────────────────────────────────────────────
#
# Koordinaten wie beim alten Baum: viewBox -20 -10 580 500, Boden bei y = 490.

BODEN = 490

STAMM: list[Knoten] = [
    (250, BODEN + 2, 86),
    (250, 476, 66),
    (251, 452, 56),
    (249, 420, 51),
    (251, 386, 47),
    (249, 354, 43),
    (250, 324, 38),
]

AESTE: list[list[Knoten]] = [
    # Wurzelanläufe
    [(238, 468, 26), (214, 482, 15), (184, BODEN + 1, 5)],
    [(262, 468, 26), (288, 482, 15), (320, BODEN + 1, 5)],
    [(244, 476, 16), (230, 486, 10), (212, BODEN + 2, 3.5)],
    # großer Ast links
    [(248, 340, 32), (228, 306, 25), (196, 276, 17.5), (156, 252, 13), (112, 232, 8.5), (64, 216, 4)],
    # großer Ast rechts, trägt die Schaukel
    [(252, 342, 32), (274, 308, 25), (310, 280, 17), (352, 262, 12.5), (396, 250, 8.5), (446, 236, 4)],
    # Mitte hinauf
    [(250, 330, 28), (254, 286, 21), (246, 232, 14.5), (253, 180, 10.5), (246, 128, 6.5), (251, 74, 3)],
    # links hinauf
    [(198, 274, 13), (182, 234, 10.5), (171, 192, 8), (177, 148, 5.2), (165, 104, 2.6)],
    # rechts hinauf
    [(306, 282, 12.5), (322, 240, 10), (331, 198, 7.5), (321, 156, 4.8), (332, 112, 2.4)],
    # Zweige
    [(156, 252, 8), (128, 262, 5.5), (98, 278, 3), (80, 290, 1.8)],
    [(352, 262, 8), (384, 274, 5.5), (412, 290, 3.2), (428, 302, 1.8)],
    [(246, 236, 8), (220, 208, 5.8), (205, 176, 3.4), (200, 150, 1.8)],
    [(252, 186, 7), (280, 162, 5), (292, 132, 2.6)],
    [(172, 194, 6), (140, 174, 4.2), (114, 154, 2.2)],
    [(329, 200, 6), (362, 180, 4.2), (390, 160, 2.2)],
    [(112, 232, 5.5), (86, 208, 3.4), (70, 186, 1.8)],
    [(396, 250, 5.5), (424, 226, 3.4), (440, 204, 1.8)],
    [(177, 150, 4), (196, 120, 2.8), (206, 94, 1.6)],
    [(321, 158, 4), (300, 128, 2.8), (292, 100, 1.6)],
]

# Die Krone: Vereinigung von Ellipsen. Sie deckt die Klemm-Ellipsen (CROWN)
# aus tree.html vollständig ab, damit keine Erinnerung im Himmel hängt.
KRONE: list[Ellipse] = [
    (250, 150, 196, 112),
    (148, 112, 108, 84),
    (250, 76, 116, 66),
    (352, 112, 108, 84),
    (74, 174, 70, 66),
    (426, 174, 70, 66),
    (166, 222, 108, 64),
    (334, 222, 108, 64),
    (250, 214, 120, 72),
]
KRONEN_MITTE: Punkt = (250, 170)


def kronen_licht(x: float, y: float) -> float:
    """Licht von links oben, zur Mitte der Unterseite hin Schatten."""
    oben = 1 - (y + 10) / 300
    links = (250 - x) / 700
    unten_mitte = max(0, (y - 170) / 120) * max(0, 1 - abs(x - 250) / 220) * 0.45
    return max(0.0, min(1.0, oben * 0.95 + links - unten_mitte + 0.12))


def baum() -> str:
    rand = zufall(7)

    # Rinde: feine, leicht wellige Längsrillen auf dem Stamm.
    rillen = []
    for i in range(9):
        t = (i + 0.5) / 9
        pts: list[Punkt] = []
        for x, y, w in STAMM[1:]:
            pts.append((x - w / 2 + w * (0.12 + t * 0.76) + (rand() - 0.5) * 3, y))
        seg_start = int(rand() * 2)
        pts = pts[seg_start : len(pts) - int(rand() * 2)]
        if len(pts) >= 2:
            rillen.append(f"M{f(pts[0][0])} {f(pts[0][1])}{glatt(pts)}")
    # Querrisse, wie sie Borke an alten Stämmen zeigt.
    risse = []
    for _ in range(14):
        y = 330 + rand() * 140
        halb = next(w for x, yy, w in STAMM[::-1] if yy >= y) / 2
        x = 250 + (rand() - 0.5) * halb * 1.2
        ln = 3 + rand() * 6
        risse.append(f"M{f(x - ln / 2)} {f(y)}q{f(ln / 2)} {f(1.5 + rand())} {f(ln)} 0")

    aeste = "".join(f'<path d="{ast(k)}"/>' for k in [STAMM, *AESTE])
    schatten_stamm = ast(versetzt(STAMM, 11, 0.42))
    licht_stamm = ast(versetzt(STAMM, -12, 0.2))
    aeste_licht = "".join(
        f'<path d="{ast(versetzt(k, -k[0][2] * 0.22, 0.3))}"/>' for k in AESTE[3:8]
    )

    # Grund der Krone: dunkle Fläche, darüber eine hellere, nach links oben versetzt.
    grund_dunkel = "".join(
        f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx - 6)}" ry="{f(ry - 6)}"/>'
        for cx, cy, rx, ry in KRONE
    )
    grund_hell = "".join(
        f'<ellipse cx="{f(cx - 8)}" cy="{f(cy - 12)}" rx="{f(rx - 22)}" ry="{f(ry - 24)}"/>'
        for cx, cy, rx, ry in KRONE
    )

    # Blätter hinter den Ästen: dunkel, sie machen die Tiefe.
    hinten = laub(
        rand, KRONE, mitte=KRONEN_MITTE, rand_blaetter=260, gesamt=700,
        groesse=15, licht=lambda x, y: kronen_licht(x, y) * 0.45, toene=3,
    )
    # Blätter vor den Ästen: der eigentliche Umriss, fünf Töne.
    vorn = laub(
        rand, KRONE, mitte=KRONEN_MITTE, rand_blaetter=560, gesamt=1500,
        groesse=14, licht=kronen_licht, toene=6,
    )
    # Ein paar Lichttupfer ganz oben links: fast gelbgrün.
    tupfer = laub(
        rand, [(170, 70, 110, 55), (250, 34, 90, 40), (110, 130, 60, 50)],
        mitte=KRONEN_MITTE, rand_blaetter=40, gesamt=150, groesse=12,
        licht=lambda x, y: 1.0, toene=1, innen_abstand=0,
    )

    farben_hinten = ["#123d1c", "#174922", "#1c5226"]
    farben_vorn = ["#1b4f25", "#22602d", "#2c7338", "#3a8744", "#56a052", "#7cbb62"]

    # Äste, die zwischen den Blättern hindurchscheinen (nur die inneren Stücke).
    durchblick = "".join(
        f'<path d="{ast(k[1:])}"/>' for k in AESTE[3:8] + AESTE[10:14] if len(k) > 2
    )

    # Schaukel am rechten großen Ast.
    schaukel = (
        '<g class="schaukel">'
        '<path d="M374 262C372 300 369 330 367 366" stroke="#8a6a44" stroke-width="2.2" fill="none" stroke-linecap="round"/>'
        '<path d="M396 256C398 296 400 330 401 366" stroke="#8a6a44" stroke-width="2.2" fill="none" stroke-linecap="round"/>'
        '<path d="M374 262C372 300 369 330 367 366" stroke="#c8a676" stroke-width="0.7" fill="none" stroke-dasharray="2 3" opacity="0.8"/>'
        '<path d="M396 256C398 296 400 330 401 366" stroke="#c8a676" stroke-width="0.7" fill="none" stroke-dasharray="2 3" opacity="0.8"/>'
        '<ellipse cx="374" cy="262" rx="3.2" ry="2.6" fill="#7a5a38"/>'
        '<ellipse cx="396" cy="256" rx="3.2" ry="2.6" fill="#7a5a38"/>'
        '<rect x="359" y="365" width="50" height="8" rx="2.5" fill="#8d6a45"/>'
        '<rect x="359" y="365" width="50" height="3" rx="1.5" fill="#b08a5e"/>'
        '<path d="M364 370h8M378 369.5h14M398 370h6" stroke="#6e5033" stroke-width="0.6"/>'
        "</g>"
    )

    # Boden am Stamm: Schatten der Krone, Moos am Stammfuß, Gras davor.
    boden = (
        f'<ellipse cx="258" cy="{BODEN}" rx="190" ry="14" fill="#1f4d27" opacity="0.28"/>'
        f'<ellipse cx="250" cy="{BODEN - 1}" rx="70" ry="6" fill="#1a3f20" opacity="0.35"/>'
    )
    moos = "".join(
        f'<ellipse cx="{f(214 + rand() * 72)}" cy="{f(BODEN - 3 - rand() * 8)}" '
        f'rx="{f(3 + rand() * 5)}" ry="{f(1.6 + rand() * 2)}" fill="{["#4d7a3a", "#5f8f45", "#3f6b33"][int(rand() * 3)]}"/>'
        for _ in range(14)
    )
    gras = []
    for i in range(70):
        x = 150 + rand() * 200
        h = 6 + rand() * 12
        neig = (rand() - 0.5) * 8
        gras.append(f"M{f(x)} {BODEN + 2}q{f(neig * 0.3)} {f(-h * 0.6)} {f(neig)} {f(-h)}")
    gras_d = "".join(gras)

    stil = (
        ".schaukel{transform-origin:385px 259px;animation:schaukeln 5.5s ease-in-out infinite}"
        "@keyframes schaukeln{0%,100%{transform:rotate(-2.2deg)}50%{transform:rotate(2.2deg)}}"
        ".wind{transform-origin:250px 330px;animation:wind 9s ease-in-out infinite}"
        "@keyframes wind{0%,100%{transform:rotate(-.35deg)}50%{transform:rotate(.35deg)}}"
        + RUHE
    )

    body = (
        boden
        + f'<g fill="#4a3324">{aeste}</g>'
        + f'<path fill="#3a2819" opacity="0.55" d="{schatten_stamm}"/>'
        + f'<path fill="#8a6548" opacity="0.7" d="{licht_stamm}"/>'
        + f'<g fill="#7a5a40" opacity="0.55">{aeste_licht}</g>'
        + f'<g fill="none" stroke="#2e1f14" stroke-width="1.1" stroke-linecap="round" opacity="0.45">'
        + "".join(f'<path d="{d}"/>' for d in rillen)
        + "</g>"
        + f'<path fill="none" stroke="#2e1f14" stroke-width="1" stroke-linecap="round" opacity="0.5" d="{"".join(risse)}"/>'
        + '<ellipse cx="238" cy="398" rx="4.5" ry="7" fill="#2e1f14" opacity="0.7"/>'
        + '<ellipse cx="238.6" cy="398.6" rx="2.6" ry="4.6" fill="#1c130c"/>'
        + '<path d="M232 390c3-4 9-4 12 0" stroke="#7a5a40" stroke-width="1.4" fill="none" opacity="0.8"/>'
        + moos
        + '<g class="wind">'
        + f'<g fill="#163f1f">{grund_dunkel}</g>'
        + laub_svg(hinten, farben_hinten)
        + f'<g fill="#1f5529" opacity="0.9">{grund_hell}</g>'
        + f'<g fill="#3d2a1c" opacity="0.9">{durchblick}</g>'
        + laub_svg(vorn, farben_vorn)
        + laub_svg(tupfer, ["#a3cf78"])
        + "</g>"
        + schaukel
        + f'<path d="{gras_d}" stroke="#3f7d3f" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
    )
    return svg("-20 -10 580 500", body, style=stil)


# ── Blätterkranz vor den Fotos ──────────────────────────────────────────────


def blaetterkranz(seed: int) -> str:
    """Ein paar Blätter und ein Zweig, die über den Rand eines Fotos ragen.

    Das Foto ist in der Seite ein HTML-Element über dem Baum. Diese Datei
    liegt als Bild über seinem Rahmen, damit es im Laub hängt, statt auf
    der Krone zu kleben. Das Foto füllt 0–100, das Feld reicht 30 darüber
    hinaus; die Seite legt das Bild deshalb mit 160 % Größe und −30 % Versatz.
    """
    rand = zufall(seed)
    gruppen: list[list[str]] = [[], [], [], []]
    farben = ["#1f5a2a", "#2c7338", "#3f8c45", "#6aae58"]
    zweig = ""
    ecken = [(0, 0, -2.4), (100, 0, -0.7), (100, 100, 0.8), (0, 100, 2.4)]
    gewaehlt = [ecken[seed % 4], ecken[(seed + 2) % 4]]
    for i, (ex, ey, richtung) in enumerate(gewaehlt):
        anzahl = 7 if i == 0 else 4
        for _ in range(anzahl):
            w = richtung + (rand() - 0.5) * 1.6
            d = 4 + rand() * 12
            x, y = ex + math.cos(w) * d, ey + math.sin(w) * d
            ton = min(3, int(rand() * 4))
            ln = 11 + rand() * 6
            gruppen[ton].append(blatt_pfad(x, y, w + (rand() - 0.5) * 1.2, ln, ln * 0.5))
        if i == 0:
            zx, zy = ex + math.cos(richtung) * 16, ey + math.sin(richtung) * 16
            zweig = (
                f'<path d="M{f(ex - math.cos(richtung) * 10)} {f(ey - math.sin(richtung) * 10)}'
                f'Q{f(ex)} {f(ey + 3)} {f(zx)} {f(zy)}" stroke="#4a3324" stroke-width="2.2" '
                f'fill="none" stroke-linecap="round"/>'
            )
    body = zweig + laub_svg(gruppen, farben)
    return svg("-30 -30 160 160", body)


# ── Hügel und Ferne ─────────────────────────────────────────────────────────


def huegellinie(rand: Callable[[], float], breite: float, y: float, amp: float, n: int) -> list[Punkt]:
    pts = []
    for i in range(n + 1):
        x = -40 + (breite + 80) * i / n
        pts.append((x, y + math.sin(i * 1.7 + rand() * 2) * amp * 0.6 + (rand() - 0.5) * amp))
    return pts


def huegel_form(pts: list[Punkt], unten: float) -> str:
    return f"M{f(pts[0][0])} {f(pts[0][1])}{glatt(pts)}L{f(pts[-1][0])} {f(unten)}L{f(pts[0][0])} {f(unten)}Z"


def hoehe_bei(pts: list[Punkt], x: float) -> float:
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            t = t * t * (3 - 2 * t)
            return y0 + (y1 - y0) * t
    return pts[-1][1]


def baeumchen(rand: Callable[[], float], x: float, y: float, h: float, farbe: str, hell: str) -> str:
    """Ein ferner Baum: Laubbaum aus drei Kreisen oder eine schmale Tanne."""
    if rand() < 0.35:
        b = h * 0.32
        return (
            f'<path fill="{farbe}" d="M{f(x)} {f(y - h)}L{f(x + b)} {f(y)}L{f(x - b)} {f(y)}Z"/>'
        )
    r = h * 0.36
    return (
        f'<rect fill="{farbe}" x="{f(x - h * 0.05)}" y="{f(y - h * 0.4)}" width="{f(h * 0.1)}" height="{f(h * 0.4)}"/>'
        f'<circle fill="{farbe}" cx="{f(x)}" cy="{f(y - h * 0.6)}" r="{f(r)}"/>'
        f'<circle fill="{farbe}" cx="{f(x - r * 0.6)}" cy="{f(y - h * 0.48)}" r="{f(r * 0.72)}"/>'
        f'<circle fill="{farbe}" cx="{f(x + r * 0.62)}" cy="{f(y - h * 0.5)}" r="{f(r * 0.7)}"/>'
        f'<circle fill="{hell}" cx="{f(x - r * 0.3)}" cy="{f(y - h * 0.7)}" r="{f(r * 0.45)}"/>'
    )


def huegel() -> str:
    """Ferne Berge, Hügel mit Baumreihen und Hecken. Feld 1920 × 520."""
    rand = zufall(21)
    B, H = 1920, 520
    teile: list[str] = []

    # Berge ganz hinten, mit Schneekuppen: die Beispielpaare wandern im Allgäu.
    # Jeder Gipfel mit Schultern links und rechts, damit die Kette nicht
    # aus gleichförmigen Dreiecken besteht.
    berg_pts: list[Punkt] = []
    x = -80.0
    while x < B + 160:
        tal = 300 + rand() * 24
        gipfel = 196 + rand() * 50
        breite = 150 + rand() * 120
        berg_pts.append((x, tal))
        berg_pts.append((x + breite * (0.2 + rand() * 0.1), gipfel + 34 + rand() * 18))
        berg_pts.append((x + breite * 0.5, gipfel))
        berg_pts.append((x + breite * (0.72 + rand() * 0.1), gipfel + 28 + rand() * 22))
        x += breite
    berg = "M" + " L".join(f"{f(px)} {f(py)}" for px, py in berg_pts) + f" L{B + 160} {H} L-80 {H}Z"
    teile.append(f'<path fill="#a9c6cf" d="{berg}"/>')
    # Schatten der Nordflanken und Schnee auf den Gipfeln.
    schatten, schnee = [], []
    for i in range(2, len(berg_pts) - 2, 4):
        schulter_l, (gx, gy), schulter_r = berg_pts[i - 1], berg_pts[i], berg_pts[i + 1]
        tal_r = berg_pts[i + 2]
        schatten.append(
            f"M{f(gx)} {f(gy)}L{f(schulter_r[0])} {f(schulter_r[1])}L{f(tal_r[0])} {f(tal_r[1])}"
            f"L{f(tal_r[0] - 20)} {f(H)}L{f(gx + 6)} {f(H)}Z"
        )
        if gy < 228:
            t = 0.38 + rand() * 0.12
            lx, ly = gx + (schulter_l[0] - gx) * t, gy + (schulter_l[1] - gy) * t
            rx, ry = gx + (schulter_r[0] - gx) * t, gy + (schulter_r[1] - gy) * t
            schnee.append(
                f"M{f(gx)} {f(gy)}L{f(rx)} {f(ry)}L{f(rx - 7)} {f(ry - 2)}L{f(gx + 3)} {f(ry + 3)}"
                f"L{f(gx - 6)} {f(ly - 1)}L{f(lx + 5)} {f(ly + 3)}L{f(lx)} {f(ly)}Z"
            )
    teile.append(f'<path fill="#8fb1bd" d="{"".join(schatten)}"/>')
    teile.append(f'<path fill="#eef5f7" d="{"".join(schnee)}"/>')
    # Dunst über den Bergen.
    teile.append(f'<rect x="0" y="200" width="{B}" height="{H - 200}" fill="url(#dunst)"/>')

    schichten = [
        # y, Amplitude, Farbe, Baumfarbe, Lichtfarbe, Baumhöhe, Dichte
        (318, 36, "#9cc3a4", "#86b391", "#a9cdb0", 16, 0.012),
        (360, 40, "#80b18a", "#5f9a6c", "#8cbf93", 24, 0.016),
        (405, 36, "#62995f", "#4a8350", "#74ab6c", 34, 0.012),
    ]
    for i, (y, amp, farbe, bf, hell, bh, dichte) in enumerate(schichten):
        pts = huegellinie(rand, B, y, amp, 9)
        teile.append(f'<path fill="{farbe}" d="{huegel_form(pts, H)}"/>')
        # Felder: hellere Streifen, die der Hügelkante folgen.
        if i > 0:
            for _ in range(3):
                x0 = rand() * B
                w = 160 + rand() * 260
                yy = hoehe_bei(pts, x0 + w / 2) + 18 + rand() * 20
                teile.append(
                    f'<path fill="{hell}" opacity="0.55" d="M{f(x0)} {f(yy)}'
                    f'q{f(w / 2)} {f(-10 - rand() * 8)} {f(w)} {f(2 + rand() * 6)}'
                    f'l{f(-10)} {f(10)}q{f(-w / 2)} {f(-8)} {f(-w + 10)} {f(-2)}Z"/>'
                )
        # Baumreihen und einzelne Bäume auf der Kante.
        x = rand() * 40
        while x < B:
            if rand() < dichte * 40:
                cluster = 1 + int(rand() * 5)
                for _ in range(cluster):
                    xx = x + rand() * bh * 1.4
                    h = bh * (0.7 + rand() * 0.6)
                    teile.append(baeumchen(rand, xx, hoehe_bei(pts, xx) + 3, h, bf, hell))
                    x = xx
            x += bh * (1.2 + rand() * 3)
        # Hecken als dunkle, weiche Linie über den nächsten Hügel.
        if i == 2:
            for _ in range(4):
                x0 = rand() * B
                yy = hoehe_bei(pts, x0) + 26 + rand() * 30
                w = 120 + rand() * 180
                blobs = "".join(
                    f'<ellipse cx="{f(x0 + j * 7)}" cy="{f(yy - math.sin(j / 4) * 3 + (rand() - 0.5) * 1.5)}" rx="{f(4.5 + rand() * 2)}" ry="{f(2.8 + rand() * 1.4)}"/>'
                    for j in range(int(w / 7))
                )
                teile.append(f'<g fill="{bf}" opacity="0.7">{blobs}</g>')

    defs = (
        '<defs><linearGradient id="dunst" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#dcebf0" stop-opacity="0"/>'
        '<stop offset="0.6" stop-color="#dcebf0" stop-opacity="0.55"/>'
        '<stop offset="1" stop-color="#dcebf0" stop-opacity="0.15"/>'
        "</linearGradient></defs>"
    )
    return svg(f"0 0 {B} {H}", defs + "".join(teile), extra=' preserveAspectRatio="xMidYMax slice"')


# ── Wolken ──────────────────────────────────────────────────────────────────


def wolke(seed: int, breite: float) -> str:
    """Eine Haufenwolke: flache Unterseite, bauschige Oberseite, Schatten unten."""
    rand = zufall(seed)
    h = breite * 0.42
    kreise: list[tuple[float, float, float]] = []
    n = 5 + int(rand() * 3)
    for i in range(n):
        t = (i + 0.5) / n
        r = breite * (0.1 + 0.12 * math.sin(t * math.pi)) * (0.85 + rand() * 0.3)
        kreise.append((breite * (0.1 + t * 0.8), h - r * 0.55 - rand() * r * 0.2, r))
    for _ in range(3):
        t = 0.3 + rand() * 0.4
        r = breite * (0.13 + rand() * 0.06)
        kreise.append((breite * t, h - r * 1.15, r))

    def c(dx: float, dy: float, fak: float) -> str:
        return "".join(
            f'<circle cx="{f(x + dx)}" cy="{f(y + dy)}" r="{f(r * fak)}"/>' for x, y, r in kreise
        )

    body = (
         f'<clipPath id="u{seed}"><rect x="0" y="{f(-h)}" width="{f(breite)}" height="{f(h * 2)}"/></clipPath>'
        f'<g clip-path="url(#u{seed})">'
        f'<g fill="#d5e3ee">{c(0, 0, 1)}</g>'
        f'<g fill="#eef4f9">{c(-2, -4, 0.94)}</g>'
        f'<g fill="#ffffff">{c(-5, -8, 0.8)}</g>'
        "</g>"
        f'<rect x="{f(breite * 0.1)}" y="{f(h - 3)}" width="{f(breite * 0.8)}" height="3" rx="1.5" fill="#d5e3ee"/>'
    )
    return svg(f"0 {f(-h * 0.25)} {f(breite)} {f(h * 1.25)}", body)


# ── Wiese ───────────────────────────────────────────────────────────────────


def bluete(rand: Callable[[], float], x: float, y: float, art: str, s: float) -> str:
    """Eine Wiesenblume an ihrem Stiel. ``s`` skaliert, ``y`` ist der Blütenkopf."""
    if art == "gaensebluemchen":
        blaetter = "".join(
            f'<ellipse cx="{f(x + math.cos(a) * 2.6 * s)}" cy="{f(y + math.sin(a) * 1.9 * s)}" '
            f'rx="{f(2 * s)}" ry="{f(0.9 * s)}" transform="rotate({f(math.degrees(a))} '
            f'{f(x + math.cos(a) * 2.6 * s)} {f(y + math.sin(a) * 1.9 * s)})"/>'
            for a in [i * math.pi / 6 for i in range(12)]
        )
        return f'<g fill="#ffffff">{blaetter}</g><circle cx="{f(x)}" cy="{f(y)}" r="{f(1.5 * s)}" fill="#f4c430"/>'
    if art == "mohn":
        return (
            f'<path fill="#d7263d" d="M{f(x - 4 * s)} {f(y)}q{f(0)} {f(-4.5 * s)} {f(4 * s)} {f(-4 * s)}'
            f'q{f(4 * s)} {f(-0.5 * s)} {f(4 * s)} {f(4 * s)}q{f(-4 * s)} {f(3 * s)} {f(-8 * s)} 0Z"/>'
            f'<path fill="#ef4d5b" d="M{f(x - 2.5 * s)} {f(y - 1 * s)}q{f(1 * s)} {f(-3.5 * s)} {f(3.5 * s)} {f(-2.6 * s)}'
            f'q{f(-0.5 * s)} {f(2.4 * s)} {f(-3.5 * s)} {f(2.6 * s)}Z"/>'
            f'<circle cx="{f(x)}" cy="{f(y - 1.2 * s)}" r="{f(1 * s)}" fill="#2a1414"/>'
        )
    if art == "kornblume":
        zacken = "".join(
            f'<path d="M{f(x)} {f(y)}l{f(math.cos(a - 0.3) * 3.6 * s)} {f(math.sin(a - 0.3) * 3.6 * s)}'
            f'l{f(math.cos(a) * 0.9 * s)} {f(math.sin(a) * 0.9 * s)}Z"/>'
            for a in [-math.pi / 2 + (i - 3) * 0.42 for i in range(7)]
        )
        return f'<g fill="#4f7fd9" stroke="#4f7fd9" stroke-width="{f(1.1 * s)}" stroke-linejoin="round">{zacken}</g>'
    if art == "butterblume":
        blaetter = "".join(
            f'<circle cx="{f(x + math.cos(a) * 1.8 * s)}" cy="{f(y + math.sin(a) * 1.4 * s)}" r="{f(1.6 * s)}"/>'
            for a in [i * math.pi * 2 / 5 - math.pi / 2 for i in range(5)]
        )
        return f'<g fill="#f6c915">{blaetter}</g><circle cx="{f(x)}" cy="{f(y)}" r="{f(0.9 * s)}" fill="#d99a06"/>'
    if art == "klee":
        return "".join(
            f'<circle cx="{f(x + (rand() - 0.5) * 2.2 * s)}" cy="{f(y + (rand() - 0.5) * 2.2 * s)}" r="{f(1.1 * s)}" fill="{c}"/>'
            for c in ["#c86aa3", "#d88bb8", "#e3a6c9", "#c86aa3", "#e3a6c9"]
        )
    # Glockenblume
    return (
        f'<path fill="#8d6ad1" d="M{f(x - 2.4 * s)} {f(y - 3 * s)}q{f(2.4 * s)} {f(-1.6 * s)} {f(4.8 * s)} 0'
        f'l{f(0.8 * s)} {f(4.6 * s)}l{f(-1.6 * s)} {f(-0.9 * s)}l{f(-1.6 * s)} {f(1 * s)}l{f(-1.6 * s)} {f(-1 * s)}'
        f'l{f(-1.6 * s)} {f(0.9 * s)}Z"/>'
    )


BLUMEN = ["gaensebluemchen", "gaensebluemchen", "butterblume", "mohn", "kornblume", "klee", "glocke"]


def wiese() -> str:
    """Der Vordergrund: Grasnarbe mit Halmen, Blumen, Klee und Steinen.

    Feld 1920 × 150. Die Oberkante wellt sich um y ≈ 40; darunter geht die
    Wiese in die Fläche der Seite (#4a8c54) über, auf der Datum und Knopf stehen.
    """
    rand = zufall(33)
    B, H = 1920, 150
    kante = [(x, 42 + math.sin(x / 150) * 6 + math.sin(x / 47) * 2.5) for x in range(-20, B + 41, 40)]
    teile: list[str] = []
    teile.append(
        f'<path fill="#3f7f46" d="M{f(kante[0][0])} {f(kante[0][1] - 6)}{glatt([(x, y - 6) for x, y in kante])}L{B + 20} {H}L-20 {H}Z"/>'
    )
    teile.append(f'<path fill="url(#boden)" d="M-20 {f(kante[0][1])}{glatt(kante)}L{B + 20} {H}L-20 {H}Z"/>')

    # Hintere Halme: dunkel, dicht.
    for schicht, (farben, anzahl, hoehe, y_off) in enumerate(
        [
            (["#2f6b37", "#347540", "#2b6233"], 620, 22, 0),
            (["#428a48", "#4d9950", "#3d8243"], 480, 16, 8),
        ]
    ):
        gruppen: dict[str, list[str]] = {c: [] for c in farben}
        for _ in range(anzahl):
            x = -10 + rand() * (B + 20)
            y = hoehe_bei(kante, x) + y_off + rand() * 6
            h = hoehe * (0.5 + rand() * 0.8)
            neig = (rand() - 0.5) * h * 0.7
            w = 1.2 + rand() * 1.2
            gruppen[farben[int(rand() * len(farben))]].append(
                f"M{f(x - w)} {f(y)}Q{f(x + neig * 0.2)} {f(y - h * 0.6)} {f(x + neig)} {f(y - h)}"
                f"Q{f(x + neig * 0.2 + w * 0.6)} {f(y - h * 0.5)} {f(x + w)} {f(y)}Z"
            )
        teile.append("".join(f'<path fill="{c}" d="{"".join(g)}"/>' for c, g in gruppen.items() if g))

    # Kleeblätter und Steine im Gras.
    klee = []
    for _ in range(60):
        x = rand() * B
        y = hoehe_bei(kante, x) + 20 + rand() * 60
        for k in range(3):
            a = -math.pi / 2 + k * 2 * math.pi / 3 + rand() * 0.3
            klee.append(f'<circle cx="{f(x + math.cos(a) * 2.2)}" cy="{f(y + math.sin(a) * 1.6)}" r="2.1"/>')
    teile.append(f'<g fill="#5aa257" opacity="0.8">{"".join(klee)}</g>')
    steine = []
    for _ in range(22):
        x = rand() * B
        y = hoehe_bei(kante, x) + 26 + rand() * 70
        rx = 3 + rand() * 6
        steine.append(
            f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(rx)}" ry="{f(rx * 0.55)}" fill="#8f9488"/>'
            f'<ellipse cx="{f(x - rx * 0.25)}" cy="{f(y - rx * 0.18)}" rx="{f(rx * 0.55)}" ry="{f(rx * 0.25)}" fill="#b7bbb0"/>'
        )
    teile.append("".join(steine))

    # Blumen auf der Kante: Stiel, zwei Blättchen, Blüte.
    blumen = []
    stiele = []
    for _ in range(170):
        x = rand() * B
        # Die Mitte bleibt ruhiger, dort stehen Datum und Knopf.
        if abs(x - B / 2) < 170 and rand() < 0.75:
            continue
        basis = hoehe_bei(kante, x) + 4 + rand() * 18
        h = 10 + rand() * 18
        neig = (rand() - 0.5) * 6
        stiele.append(f"M{f(x)} {f(basis)}q{f(neig * 0.3)} {f(-h / 2)} {f(neig)} {f(-h)}")
        art = BLUMEN[int(rand() * len(BLUMEN))]
        blumen.append(bluete(rand, x + neig, basis - h, art, 0.9 + rand() * 0.5))
    teile.append(f'<path d="{"".join(stiele)}" stroke="#2f6b37" stroke-width="1.1" fill="none"/>')
    teile.append("".join(blumen))

    # Vordere Halme: hell, laufen über die Blumenstiele.
    vorn: list[str] = []
    for _ in range(300):
        x = rand() * B
        y = hoehe_bei(kante, x) + 14 + rand() * 10
        h = 8 + rand() * 12
        neig = (rand() - 0.5) * h * 0.8
        vorn.append(f"M{f(x - 1)} {f(y)}Q{f(x + neig * 0.2)} {f(y - h * 0.6)} {f(x + neig)} {f(y - h)}Q{f(x + 0.6)} {f(y - h * 0.5)} {f(x + 1)} {f(y)}Z")
    teile.append(f'<path fill="#5fae5f" d="{"".join(vorn)}"/>')

    defs = (
        '<defs><linearGradient id="boden" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#4f9a55"/><stop offset="0.45" stop-color="#4a8c54"/>'
        '<stop offset="1" stop-color="#4a8c54"/></linearGradient></defs>'
    )
    return svg(f"0 0 {B} {H}", defs + "".join(teile), extra=' preserveAspectRatio="xMidYMin slice"')


# ── Rasenfläche ─────────────────────────────────────────────────────────────


def rasen() -> str:
    """Kachel für die Rasenfläche unter der Wiese: Halme, Klee, ein paar Blüten.

    Nahtlos kachelbar (160 × 120), dezent auf dem Grün der Seite (#4a8c54),
    damit Datum und Knopf lesbar bleiben.
    """
    rand = zufall(91)
    B, H = 160, 120
    halme: list[str] = []
    hell: list[str] = []
    klee: list[str] = []
    blueten: list[str] = []
    for _ in range(46):
        x, y = rand() * B, rand() * H
        h = 4 + rand() * 5
        neig = (rand() - 0.5) * 4
        ziel = halme if rand() < 0.6 else hell
        for dx in (-B, 0, B):
            ziel.append(f"M{f(x + dx - 0.7)} {f(y)}q{f(0.7 + neig * 0.3)} {f(-h * 0.6)} {f(0.7 + neig)} {f(-h)}q{f(-neig * 0.5 + 0.2)} {f(h * 0.5)} {f(0.7 - neig)} {f(h)}Z")
    for _ in range(7):
        x, y = rand() * (B - 12) + 6, rand() * (H - 12) + 6
        for k in range(3):
            a = -math.pi / 2 + k * 2 * math.pi / 3
            klee.append(f'<circle cx="{f(x + math.cos(a) * 1.8)}" cy="{f(y + math.sin(a) * 1.4)}" r="1.7"/>')
    for _ in range(3):
        x, y = rand() * (B - 12) + 6, rand() * (H - 12) + 6
        blueten.append(bluete(rand, x, y, ["gaensebluemchen", "klee", "butterblume"][int(rand() * 3)], 0.7))
    body = (
        f'<path fill="#3f7f48" d="{"".join(halme)}"/>'
        f'<path fill="#56a05c" opacity="0.7" d="{"".join(hell)}"/>'
        f'<g fill="#5aa257" opacity="0.7">{"".join(klee)}</g>'
        f'<g opacity="0.8">{"".join(blueten)}</g>'
    )
    return svg(f"0 0 {B} {H}", body, extra=f' width="{B}" height="{H}"')


# ── Zaun ────────────────────────────────────────────────────────────────────


def holz_maserung(rand: Callable[[], float], x: float, y: float, w: float, h: float, laengs: bool) -> str:
    """Feine Maserung auf einem Brett oder Pfosten."""
    linien = []
    for _ in range(3 if laengs else 2):
        if laengs:
            xx = x + w * (0.2 + rand() * 0.6)
            linien.append(
                f"M{f(xx)} {f(y + 3)}q{f((rand() - 0.5) * 3)} {f(h * 0.5)} {f((rand() - 0.5) * 2)} {f(h - 6)}"
            )
        else:
            yy = y + h * (0.25 + rand() * 0.5)
            linien.append(
                f"M{f(x + 4)} {f(yy)}q{f(w * 0.5)} {f((rand() - 0.5) * 2.5)} {f(w - 8)} {f((rand() - 0.5) * 1.5)}"
            )
    return "".join(linien)


def zaun(seed: int, ranke: str) -> str:
    """Ein verwitterter Holzzaun aus Spaltbalken, mit Moos, Gras und Ranke.

    Feld 300 × 170, Boden bei y ≈ 160. ``ranke`` ist ``"rose"`` oder ``"efeu"``.
    """
    rand = zufall(seed)
    teile: list[str] = []
    maser: list[str] = []
    boden = 160
    pfosten = [(24, -2), (150, 1.5), (276, -1)]
    # Schatten auf dem Boden.
    teile.append(f'<ellipse cx="150" cy="{boden + 2}" rx="148" ry="5" fill="#1f4d27" opacity="0.28"/>')

    # Balken hinter den Pfosten, leicht durchhängend und schief.
    for yb in (52, 96):
        y0 = yb + (rand() - 0.5) * 4
        y1 = yb + (rand() - 0.5) * 4
        d = (
            f"M-6 {f(y0)}Q150 {f((y0 + y1) / 2 + 2.5)} 306 {f(y1)}"
            f"L306 {f(y1 + 13)}Q150 {f((y0 + y1) / 2 + 15.5)} -6 {f(y0 + 12)}Z"
        )
        teile.append(f'<path fill="#8a6b4e" d="{d}"/>')
        teile.append(
            f'<path fill="#a8876a" d="M-6 {f(y0)}Q150 {f((y0 + y1) / 2 + 2.5)} 306 {f(y1)}L306 {f(y1 + 4)}Q150 {f((y0 + y1) / 2 + 6.5)} -6 {f(y0 + 4)}Z"/>'
        )
        teile.append(
            f'<path fill="#6d5139" d="M-6 {f(y0 + 10)}Q150 {f((y0 + y1) / 2 + 12.5)} 306 {f(y1 + 11)}L306 {f(y1 + 13)}Q150 {f((y0 + y1) / 2 + 15.5)} -6 {f(y0 + 12)}Z"/>'
        )
        maser.append(holz_maserung(rand, 0, y0, 300, 12, False))
        # Ein Riss im Balken.
        rx = 60 + rand() * 180
        maser.append(f"M{f(rx)} {f(y0 + 6)}l{f(14 + rand() * 10)} {f((rand() - 0.5) * 2)}")

    for px, neig in pfosten:
        hoehe = 128 + rand() * 12
        top = boden - hoehe
        w = 20
        d = (
            f"M{f(px - w / 2 + neig * 0.5)} {f(top + 6)}Q{f(px + neig * 0.5)} {f(top - 3)} {f(px + w / 2 + neig * 0.5)} {f(top + 6)}"
            f"L{f(px + w / 2 + 1)} {f(boden)}L{f(px - w / 2 - 1)} {f(boden)}Z"
        )
        teile.append(f'<path fill="#7f6147" d="{d}"/>')
        teile.append(
            f'<path fill="#a07e5f" d="M{f(px - w / 2 + neig * 0.5)} {f(top + 6)}Q{f(px - 2 + neig * 0.5)} {f(top)} {f(px - 1 + neig * 0.5)} {f(top + 2)}L{f(px - 3)} {f(boden)}L{f(px - w / 2 - 1)} {f(boden)}Z"/>'
        )
        teile.append(
            f'<path fill="#5f4633" d="M{f(px + w / 2 - 4 + neig * 0.5)} {f(top + 5)}L{f(px + w / 2 + neig * 0.5)} {f(top + 6)}L{f(px + w / 2 + 1)} {f(boden)}L{f(px + w / 2 - 3)} {f(boden)}Z"/>'
        )
        # Kopf mit Jahresringen.
        teile.append(
            f'<ellipse cx="{f(px + neig * 0.5)}" cy="{f(top + 5)}" rx="{f(w / 2)}" ry="4" fill="#b8997a"/>'
            f'<ellipse cx="{f(px + neig * 0.5)}" cy="{f(top + 5)}" rx="{f(w / 2 - 4)}" ry="2.3" fill="none" stroke="#8f7050" stroke-width="0.6"/>'
            f'<ellipse cx="{f(px + neig * 0.5)}" cy="{f(top + 5)}" rx="2" ry="1" fill="#8f7050"/>'
        )
        maser.append(holz_maserung(rand, px - w / 2, top + 8, w, hoehe - 10, True))
        # Ast im Holz.
        ay = top + 30 + rand() * 60
        teile.append(
            f'<ellipse cx="{f(px + (rand() - 0.5) * 6)}" cy="{f(ay)}" rx="2.2" ry="3.4" fill="#5f4633"/>'
        )
        # Nägel an den Balken.
        for yb in (58, 102):
            teile.append(f'<circle cx="{f(px - 4)}" cy="{f(yb)}" r="1.3" fill="#3d3a36"/>')
            teile.append(f'<circle cx="{f(px + 4)}" cy="{f(yb + 1)}" r="1.3" fill="#3d3a36"/>')
        # Moos am Fuß.
        moos = "".join(
            f'<ellipse cx="{f(px - 10 + rand() * 20)}" cy="{f(boden - 2 - rand() * 14)}" rx="{f(2.5 + rand() * 3)}" ry="{f(1.5 + rand() * 1.5)}"/>'
            for _ in range(7)
        )
        teile.append(f'<g fill="#5d8a3e" opacity="0.85">{moos}</g>')

    teile.append(
        f'<path d="{"".join(maser)}" stroke="#5a412d" stroke-width="0.7" fill="none" opacity="0.55" stroke-linecap="round"/>'
    )

    # Ranke am mittleren Pfosten.
    rp = pfosten[1][0]
    if ranke == "rose":
        pts: list[Punkt] = []
        for i in range(10):
            pts.append((rp + math.sin(i * 1.1) * 12, boden - 4 - i * 13))
        teile.append(f'<path d="M{f(pts[0][0])} {f(pts[0][1])}{glatt(pts)}" stroke="#3d6b2e" stroke-width="1.6" fill="none"/>')
        blaetter: list[str] = []
        rosen = []
        for i, (x, y) in enumerate(pts[1:], 1):
            for s in (-1, 1):
                blaetter.append(blatt_pfad(x + s * 5, y + 2, math.pi / 2 - s * 1.1, 9, 4.5))
            if i % 2 == 0:
                rx, ry = x + (rand() - 0.5) * 10, y - 2
                rosen.append(
                    f'<circle cx="{f(rx)}" cy="{f(ry)}" r="4.6" fill="#c9304f"/>'
                    f'<path d="M{f(rx - 2.6)} {f(ry)}a2.6 2.6 0 1 1 5 .8" stroke="#8f1d38" stroke-width="0.9" fill="none"/>'
                    f'<circle cx="{f(rx - 1)}" cy="{f(ry - 1.4)}" r="1.4" fill="#e6597a"/>'
                )
        teile.append(f'<path fill="#3f7a35" d="{"".join(blaetter)}"/>')
        teile.append("".join(rosen))
    else:
        # Stiel den Pfosten hinauf, dann den oberen Balken entlang nach rechts.
        pts = [(rp + math.sin(i * 0.9) * 7, boden - 2 - i * 14) for i in range(8)]
        pts += [(rp + 14 + i * 16, 58 + math.sin(i * 1.3) * 4) for i in range(6)]
        teile.append(f'<path d="M{f(pts[0][0])} {f(pts[0][1])}{glatt(pts)}" stroke="#3b5e2b" stroke-width="1.5" fill="none"/>')
        dunkel: list[str] = []
        hell: list[str] = []
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            for k in range(3):
                t = (k + rand()) / 3
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                s = 1 if (i + k) % 2 else -1
                a = math.atan2(y1 - y0, x1 - x0) + s * (1.2 + rand() * 0.5)
                ziel = dunkel if rand() < 0.5 else hell
                ziel.append(blatt_pfad(x + math.cos(a) * 4, y + math.sin(a) * 4, a, 8 + rand() * 3, 5.5))
        teile.append(f'<path fill="#2f6a33" d="{"".join(dunkel)}"/>')
        teile.append(f'<path fill="#4a8a3f" d="{"".join(hell)}"/>')

    # Gras vor dem Zaun.
    gras = []
    for _ in range(90):
        x = rand() * 300
        h = 8 + rand() * 20
        neig = (rand() - 0.5) * h * 0.6
        gras.append(f"M{f(x - 1.2)} {boden + 4}Q{f(x)} {f(boden - h * 0.5)} {f(x + neig)} {f(boden - h)}Q{f(x + 0.6)} {f(boden - h * 0.4)} {f(x + 1.2)} {boden + 4}Z")
    teile.append(f'<path fill="#3d7f45" d="{"".join(gras[:50])}"/>')
    teile.append(f'<path fill="#56a05a" d="{"".join(gras[50:])}"/>')
    return svg("0 0 300 170", "".join(teile))


# ── Bank ────────────────────────────────────────────────────────────────────


def bank() -> str:
    """Eine Gartenbank aus Holzlatten mit gusseisernen Wangen.

    Auf ihr liegt eine karierte Decke, daneben stehen zwei Tassen: ein Platz
    für zwei. Feld 220 × 150, Boden bei y ≈ 140.
    """
    rand = zufall(51)
    teile: list[str] = []
    boden = 140
    teile.append(f'<ellipse cx="110" cy="{boden}" rx="100" ry="6" fill="#1f4d27" opacity="0.32"/>')

    eisen = "#2f3431"
    eisen_hell = "#56605a"

    def seite(x: float, s: int) -> str:
        """Eine gusseiserne Seite von vorn: Pfosten, Armlehne, Bein mit Schnörkel.

        ``s`` ist −1 für links und 1 für rechts, damit der Schnörkel nach außen zeigt.
        """
        return (
            # Pfosten der Lehne, oben mit Knauf
            f'<path fill="{eisen}" d="M{f(x - 3)} 24h6l-.6 88h-4.8Z"/>'
            f'<circle cx="{f(x)}" cy="22" r="4" fill="{eisen}"/>'
            f'<circle cx="{f(x - 1.2)}" cy="20.8" r="1.3" fill="{eisen_hell}"/>'
            f'<path d="M{f(x - 1.4)} 28v80" stroke="{eisen_hell}" stroke-width="0.9"/>'
            # Bein: vom Sitz geschwungen nach außen auf den Boden
            f'<path fill="none" stroke="{eisen}" stroke-width="5.5" stroke-linecap="round" '
            f'd="M{f(x)} 112q{f(s * 2)} 14 {f(s * 9)} {boden - 116}"/>'
            f'<path fill="none" stroke="{eisen_hell}" stroke-width="1" '
            f'd="M{f(x - s * 1.5)} 114q{f(s * 2)} 13 {f(s * 8.5)} {boden - 120}"/>'
            f'<ellipse cx="{f(x + s * 10)}" cy="{boden - 1}" rx="5" ry="2" fill="{eisen}"/>'
            # Schnörkel zwischen Bein und Sitz
            f'<path fill="none" stroke="{eisen}" stroke-width="2.2" stroke-linecap="round" '
            f'd="M{f(x - s * 1)} 118q{f(-s * 12)} 2 {f(-s * 12)} 10q0 6 {f(s * 5)} 5q{f(s * 4)} -2 {f(s * 1)} -6"/>'
        )

    # Rückenlehne: fünf Latten zwischen den Pfosten, mit Licht oben und Schatten unten.
    maser: list[str] = []
    for i in range(5):
        y = 30 + i * 11
        teile.append(f'<rect x="18" y="{y}" width="184" height="8.5" rx="2" fill="#9b6f45"/>')
        teile.append(f'<rect x="18" y="{y}" width="184" height="2.5" rx="1" fill="#c39767"/>')
        teile.append(f'<rect x="18" y="{y + 7}" width="184" height="1.5" fill="#6e4c2d"/>')
        maser.append(holz_maserung(rand, 18, y, 184, 8, False))
    # Schatten der Lehne auf dem Sitz.
    teile.append('<rect x="16" y="86" width="188" height="6" fill="#3b2a1a" opacity="0.35"/>')
    # Sitzfläche: vier Latten in leichter Aufsicht, nach vorn heller.
    for i, farbe in enumerate(["#7f5936", "#8e6540", "#a0744a", "#b48458"]):
        y = 90 + i * 5.2
        teile.append(f'<rect x="12" y="{f(y)}" width="196" height="4.4" rx="1.5" fill="{farbe}"/>')
    teile.append('<rect x="10" y="111" width="200" height="6.5" rx="2" fill="#6e4c2d"/>')
    teile.append('<rect x="10" y="111" width="200" height="2.2" rx="1" fill="#c79a6c"/>')
    # Zarge unter dem Sitz, im Schatten.
    teile.append('<rect x="16" y="117.5" width="188" height="3" fill="#2a1f16" opacity="0.5"/>')
    teile.append(f'<path d="{"".join(maser)}" stroke="#6e4c2d" stroke-width="0.6" fill="none" opacity="0.6"/>')

    # Karierte Decke über der Lehne, die auf den Sitz fällt, rechte Hälfte.
    teile.append(
        '<path fill="#c94a47" d="M124 26L166 26Q170 60 168 92L174 94Q178 104 174 118L128 118Q124 104 126 94L125 60Z"/>'
        '<path fill="#f3e9dc" opacity="0.5" d="M133 26h5v92h-5zM150 26h5v92h-5zM161 26h3v92h-3z"/>'
        '<path fill="#f3e9dc" opacity="0.4" d="M124 40h46v5h-46zM125 62h45v5h-45zM126 84h46v5h-46zM126 104h50v5h-50z"/>'
        '<path fill="#8e2a28" opacity="0.45" d="M166 26Q170 60 168 92L174 94Q178 104 174 118L170 118Q173 102 166 96Q168 60 162 26Z"/>'
        '<path fill="#ffffff" opacity="0.18" d="M124 26h8Q130 60 131 94l-5 0Q124 60 124 26Z"/>'
        '<path d="M130 118v5M136 118v6M142 118v5M148 118v6M154 118v5M160 118v6M166 118v5M172 118v4" stroke="#c94a47" stroke-width="1.2"/>'
    )

    # Zwei Tassen auf dem Sitz, links: eine dampft noch.
    for x, farbe, dampf in ((64, "#ece5d8", True), (82, "#4f7fb0", False)):
        teile.append(
            f'<path fill="{farbe}" d="M{x - 6} 84h12l-1.2 12q-.3 2 -2.3 2h-5q-2 0 -2.3 -2Z"/>'
            f'<path d="M{x + 6} 87q5 0 4.4 4t-5 3.5" stroke="{farbe}" stroke-width="1.8" fill="none"/>'
            f'<ellipse cx="{x}" cy="84" rx="6" ry="1.5" fill="#5a3a22"/>'
            f'<path fill="#000000" opacity="0.15" d="M{x + 2} 85h4l-1.2 11q-.3 2 -2.3 2h-1Z"/>'
        )
        if dampf:
            teile.append(
                f'<g class="dampf" fill="none" stroke="#ffffff" stroke-width="1.3" stroke-linecap="round" opacity="0.7">'
                f'<path d="M{x - 2} 80q-3 -4 0 -8t0 -8"/><path d="M{x + 2} 79q-3 -4 0 -7t0 -7"/></g>'
            )

    # Seiten mit Armlehnen aus Holz.
    teile.append(seite(16, -1) + seite(204, 1))
    for x in (16, 204):
        teile.append(
            f'<path fill="#8e6540" d="M{x - 13} 70h26q4 0 4 3.5t-4 3.5h-26q-4 0 -4 -3.5t4 -3.5Z"/>'
            f'<path fill="#c39767" d="M{x - 13} 70h26q4 0 4 1.6h-34q0 -1.6 4 -1.6Z"/>'
            f'<path fill="none" stroke="{eisen}" stroke-width="2" d="M{x} 77v10"/>'
        )

    # Gras und zwei Löwenzahn um die Füße.
    gras = []
    for _ in range(70):
        x = 4 + rand() * 212
        h = 5 + rand() * 12
        neig = (rand() - 0.5) * h * 0.7
        gras.append(f"M{f(x - 1)} {boden + 3}Q{f(x)} {f(boden - h * 0.5)} {f(x + neig)} {f(boden - h)}Q{f(x + 0.5)} {f(boden - h * 0.4)} {f(x + 1)} {boden + 3}Z")
    teile.append(f'<path fill="#3d7f45" d="{"".join(gras[:35])}"/>')
    teile.append(f'<path fill="#5aa65c" d="{"".join(gras[35:])}"/>')
    teile.append(
        '<path d="M44 142q1 -8 -1 -16" stroke="#3a7a3a" stroke-width="1" fill="none"/>'
        + bluete(rand, 43, 125, "butterblume", 1.3)
        + '<path d="M176 142q-2 -9 1 -18" stroke="#3a7a3a" stroke-width="1" fill="none"/>'
        + bluete(rand, 177, 123, "gaensebluemchen", 1.2)
    )

    stil = (
        ".dampf{animation:dampf 3.6s ease-in-out infinite}"
        "@keyframes dampf{0%{opacity:0;transform:translateY(3px)}40%{opacity:.7}100%{opacity:0;transform:translateY(-5px)}}"
        + RUHE
    )
    return svg("0 0 220 150", "".join(teile), style=stil)


# ── Büsche ──────────────────────────────────────────────────────────────────


def busch(seed: int, blume: str, breite: float = 220) -> str:
    """Ein Busch aus Blättern mit Blüten, im selben Stil wie die Krone.

    Feld ``breite`` × 110, Boden bei y ≈ 104. ``blume``: ``"rose"``,
    ``"hortensie"`` oder ``"lavendel"``.
    """
    rand = zufall(seed)
    boden = 104
    ell: list[Ellipse] = []
    n = 4
    for i in range(n):
        t = (i + 0.5) / n
        cx = breite * (0.12 + t * 0.76)
        rx = breite * (0.16 + rand() * 0.06)
        ry = 26 + math.sin(t * math.pi) * 16 + rand() * 5
        ell.append((cx, boden - ry * 0.8, rx, ry))
    mitte = (breite / 2, boden - 10)
    grund = "".join(
        f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx - 4)}" ry="{f(ry - 4)}"/>' for cx, cy, rx, ry in ell
    )
    blaetter = laub(
        rand, ell, mitte=mitte, rand_blaetter=170, gesamt=420, groesse=11,
        licht=lambda x, y: max(0.0, min(1.0, 1 - (y - 20) / 90 + (breite / 2 - x) / 500)),
        toene=4, innen_abstand=9,
    )
    teile = [
        f'<ellipse cx="{f(breite / 2)}" cy="{boden}" rx="{f(breite * 0.46)}" ry="5" fill="#1f4d27" opacity="0.3"/>',
        f'<g fill="#1a4a24">{grund}</g>',
        laub_svg(blaetter, ["#1f5a2a", "#2a6e34", "#3a8541", "#5a9f50"]),
    ]
    bl = []
    for _ in range(90 if blume == "lavendel" else 16):
        for _ in range(40):
            x, y = rand() * breite, rand() * boden
            if in_ellipsen(ell, x, y, 6):
                break
        if blume == "rose":
            farbe = ["#c9304f", "#e0607e", "#f2a0b4"][int(rand() * 3)]
            bl.append(
                f'<circle cx="{f(x)}" cy="{f(y)}" r="5" fill="{farbe}"/>'
                f'<path d="M{f(x - 2.8)} {f(y + 0.4)}a2.8 2.8 0 1 1 5.4 .6" stroke="#00000033" stroke-width="1" fill="none"/>'
                f'<circle cx="{f(x - 1.2)}" cy="{f(y - 1.5)}" r="1.5" fill="#ffffff55"/>'
            )
        elif blume == "hortensie":
            farbe = ["#7d9fe0", "#a58ae0", "#c7b3f0"][int(rand() * 3)]
            bl.append(
                "".join(
                    f'<circle cx="{f(x + (rand() - 0.5) * 11)}" cy="{f(y + (rand() - 0.5) * 9)}" r="2.3" fill="{farbe}"/>'
                    for _ in range(9)
                )
                + f'<circle cx="{f(x - 2)}" cy="{f(y - 2)}" r="1.6" fill="#ffffff66"/>'
            )
        else:
            # Lavendel steht nicht im Busch, sondern ragt aus ihm heraus.
            x = breite * 0.1 + rand() * breite * 0.8
            h = 22 + rand() * 24
            y0 = boden - 26 - rand() * 20
            neig = (rand() - 0.5) * 10
            bl.append(
                f'<path d="M{f(x)} {f(y0)}q{f(neig * 0.3)} {f(-h / 2)} {f(neig)} {f(-h)}" stroke="#4f7a4a" stroke-width="1" fill="none"/>'
                + "".join(
                    f'<ellipse cx="{f(x + neig * (0.6 + k * 0.1))}" cy="{f(y0 - h * (0.6 + k * 0.1))}" rx="1.4" ry="2.2" fill="{["#8b6fd1", "#a58ae0"][k % 2]}"/>'
                    for k in range(5)
                )
            )
    teile.append("".join(bl))
    return svg(f"0 0 {f(breite)} 110", "".join(teile))


# ── Schmetterling und Vögel ─────────────────────────────────────────────────


def schmetterling(farbe: str, rand_farbe: str) -> str:
    fluegel = (
        f'<path fill="{farbe}" d="M0 0C-4 -10 -14 -12 -14 -4C-14 1 -7 2 0 0Z"/>'
        f'<path fill="{rand_farbe}" d="M0 0C-3 4 -10 8 -10 3C-10 0 -5 -1 0 0Z"/>'
        f'<circle cx="-9" cy="-5" r="1.4" fill="#ffffff" opacity="0.7"/>'
    )
    return svg(
        "-16 -14 32 26",
        f'<g class="l">{fluegel}</g><g transform="scale(-1 1)"><g class="l r">{fluegel}</g></g>'
        '<ellipse cx="0" cy="0" rx="1.2" ry="5" fill="#2b2320"/>'
        '<path d="M0 -4q-2 -4 -4 -5M0 -4q2 -4 4 -5" stroke="#2b2320" stroke-width="0.5" fill="none"/>',
        style=(
            ".l{transform-origin:0 0;animation:f .35s ease-in-out infinite alternate}"
            ".r{animation-delay:-.02s}"
            "@keyframes f{to{transform:scaleX(.25)}}"
            + RUHE
        ),
    )


def voegel() -> str:
    """Drei ferne Vögel als Striche, die mit den Flügeln schlagen."""
    teile = []
    for i, (x, y, s) in enumerate([(10, 14, 1), (34, 6, 0.8), (52, 18, 0.7)]):
        teile.append(
            f'<path class="v{i}" d="M{f(x - 7 * s)} {f(y)}q{f(3.5 * s)} {f(-4 * s)} {f(7 * s)} 0q{f(3.5 * s)} {f(-4 * s)} {f(7 * s)} 0" '
            f'stroke="#40505a" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
        )
    return svg(
        "0 0 64 26",
        "".join(teile),
        style=(
            "path{transform-box:fill-box;transform-origin:center;animation:v 1.1s ease-in-out infinite alternate}"
            ".v1{animation-delay:-.4s}.v2{animation-delay:-.8s}"
            "@keyframes v{from{transform:scaleY(1)}to{transform:scaleY(-.5)}}"
            + RUHE
        ),
    )


def main() -> None:
    print(f"Schreibe Szene nach {OUT}")
    schreibe("baum.svg", baum())
    for i in range(3):
        schreibe(f"kranz-{i}.svg", blaetterkranz(101 + i))
    schreibe("huegel.svg", huegel())
    schreibe("wolke-1.svg", wolke(61, 260))
    schreibe("wolke-2.svg", wolke(62, 190))
    schreibe("wolke-3.svg", wolke(63, 130))
    schreibe("wiese.svg", wiese())
    schreibe("rasen.svg", rasen())
    schreibe("zaun-links.svg", zaun(71, "rose"))
    schreibe("zaun-rechts.svg", zaun(72, "efeu"))
    schreibe("bank.svg", bank())
    schreibe("busch-rosen.svg", busch(81, "rose"))
    schreibe("busch-hortensie.svg", busch(82, "hortensie", 180))
    schreibe("busch-lavendel.svg", busch(83, "lavendel", 160))
    schreibe("schmetterling-1.svg", schmetterling("#f29ac0", "#e0679d"))
    schreibe("schmetterling-2.svg", schmetterling("#f6c64f", "#e39a23"))
    schreibe("voegel.svg", voegel())


if __name__ == "__main__":
    main()
