#!/usr/bin/env python3
"""
Erzeugt die Demo-Fotos für den Gastzugang unter static/demo/.

Die Bilder sind prozedural gezeichnete Szenen (Himmelsverlauf, Sonne,
Silhouetten) — keine Fremdrechte, deterministisch, klein genug fürs Repo.
Wer echte Fotos zeigen will, legt sie unter demselben Dateinamen ab; die
Thumbnails folgen der Konvention aus uploads.thumbnail_ref().

Nutzung:
    python3 scripts/make_demo_images.py

Das Ergebnis wird committet; das Skript läuft nicht beim Deploy.
"""

import math
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFilter

from demo_data import DEMO_PHOTO_DIR, demo_photo_filenames

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / DEMO_PHOTO_DIR
THUMB_DIR = OUT_DIR / "thumbs"

WIDTH, HEIGHT = 1200, 800
THUMB_SIZE = 400  # entspricht settings.THUMBNAIL_SIZE

Color = tuple[int, int, int]


def _hex(value: str) -> Color:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _mix(a: Color, b: Color, t: float) -> Color:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def _sky(stops: list[str]) -> Image.Image:
    """Vertikaler Verlauf über beliebig viele Farbstopps."""
    colors = [_hex(s) for s in stops]
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    segments = len(colors) - 1
    for y in range(HEIGHT):
        pos = y / (HEIGHT - 1) * segments
        i = min(int(pos), segments - 1)
        draw.line([(0, y), (WIDTH, y)], fill=_mix(colors[i], colors[i + 1], pos - i))
    return img


def _glow(img: Image.Image, center: tuple[int, int], radius: int, color: str) -> None:
    """Weiche Lichtscheibe (Sonne, Mond, Scheinwerfer)."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rgb = _hex(color)
    x, y = center
    draw.ellipse([x - radius * 3, y - radius * 3, x + radius * 3, y + radius * 3], fill=rgb + (60,))
    layer = layer.filter(ImageFilter.GaussianBlur(radius))
    draw = ImageDraw.Draw(layer)
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=rgb + (255,))
    img.paste(layer, (0, 0), layer)


def _ridge(draw: ImageDraw.ImageDraw, rng: random.Random, base: int, amp: int,
           color: str, jagged: bool) -> None:
    """Hügel- oder Bergkette als gefülltes Polygon."""
    points: list[tuple[float, float]] = [(0, HEIGHT)]
    phase = rng.uniform(0, math.tau)
    step = 40 if jagged else 12
    for x in range(0, WIDTH + step, step):
        wave = math.sin(x / 190 + phase) * amp + math.sin(x / 67 + phase * 2) * amp * 0.4
        if jagged:
            wave += rng.uniform(-amp, amp) * 0.5
        points.append((x, base - wave))
    points.append((WIDTH, HEIGHT))
    draw.polygon(points, fill=_hex(color))


def _water(draw: ImageDraw.ImageDraw, rng: random.Random, top: int,
           color: str, shine: str) -> None:
    draw.rectangle([0, top, WIDTH, HEIGHT], fill=_hex(color))
    for _ in range(90):
        y = rng.randint(top + 8, HEIGHT - 8)
        x = rng.randint(0, WIDTH)
        length = rng.randint(30, 160)
        draw.line([(x, y), (x + length, y)], fill=_hex(shine), width=2)


def _skyline(draw: ImageDraw.ImageDraw, rng: random.Random, base: int,
             color: str, window: str, max_h: int = 330) -> None:
    x = -10
    while x < WIDTH:
        w = rng.randint(50, 120)
        h = rng.randint(70, max_h)
        draw.rectangle([x, base - h, x + w, HEIGHT], fill=_hex(color))
        for wy in range(base - h + 14, base - 10, 26):
            for wx in range(x + 10, x + w - 12, 22):
                if rng.random() < 0.45:
                    draw.rectangle([wx, wy, wx + 9, wy + 13], fill=_hex(window))
        x += w + rng.randint(2, 14)
    draw.rectangle([0, base, WIDTH, HEIGHT], fill=_hex(color))


def _stars(draw: ImageDraw.ImageDraw, rng: random.Random, until: int, count: int) -> None:
    for _ in range(count):
        x, y = rng.randint(0, WIDTH), rng.randint(0, until)
        r = rng.choice((1, 1, 1, 2))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 240))


def _beams(img: Image.Image, rng: random.Random, colors: list[str]) -> None:
    """Bühnenlicht: farbige Kegel von oben."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for i, color in enumerate(colors):
        origin = (WIDTH * (i + 1) / (len(colors) + 1), -20)
        target = origin[0] + rng.randint(-260, 260)
        draw.polygon(
            [origin, (target - 130, HEIGHT), (target + 130, HEIGHT)],
            fill=_hex(color) + (70,),
        )
    layer = layer.filter(ImageFilter.GaussianBlur(14))
    img.paste(layer, (0, 0), layer)


def _crowd(draw: ImageDraw.ImageDraw, rng: random.Random, base: int, color: str) -> None:
    for x in range(-20, WIDTH + 40, 34):
        r = rng.randint(20, 30)
        y = base + rng.randint(-24, 24)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=_hex(color))
        draw.rectangle([x - r, y, x + r, HEIGHT], fill=_hex(color))
        if rng.random() < 0.3:  # erhobener Arm
            draw.line([(x + r, y), (x + r + 14, y - 80)], fill=_hex(color), width=11)


def _tower(draw: ImageDraw.ImageDraw, cx: int, base: int, height: int, color: str) -> None:
    """Stilisierter Gitterturm."""
    fill = _hex(color)
    top = base - height
    draw.polygon([(cx - 95, base), (cx - 8, top), (cx + 8, top), (cx + 95, base)], fill=fill)
    for frac in (0.33, 0.6):
        y = base - height * frac
        half = 95 * (1 - frac) + 14
        draw.rectangle([cx - half, y - 7, cx + half, y + 7], fill=fill)
    draw.line([(cx, top), (cx, top - 46)], fill=fill, width=4)


def _table(draw: ImageDraw.ImageDraw, rng: random.Random, accent: str) -> None:
    """Gedeckter Tisch von oben: Teller, Gläser, Kerzenlicht."""
    for _ in range(5):
        x, y = rng.randint(140, WIDTH - 140), rng.randint(330, HEIGHT - 120)
        r = rng.randint(70, 105)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(245, 240, 230))
        draw.ellipse([x - r + 16, y - r + 16, x + r - 16, y + r - 16], outline=(215, 205, 190), width=3)
        draw.ellipse([x - r // 2, y - r // 2, x + r // 2, y + r // 2], fill=_hex(accent))
    for _ in range(4):
        x, y = rng.randint(100, WIDTH - 100), rng.randint(320, HEIGHT - 80)
        draw.ellipse([x - 26, y - 26, x + 26, y + 26], fill=(120, 30, 45))
        draw.ellipse([x - 26, y - 26, x + 26, y + 26], outline=(235, 225, 225), width=3)


# ── Szenen ──────────────────────────────────────────────────────────────────

def scene_beach(rng: random.Random, dusk: bool) -> Image.Image:
    img = _sky(["#2b3a67", "#e8795a", "#f9c784"] if dusk else ["#3a8fd9", "#9fd3f0", "#f4e4c1"])
    _glow(img, (rng.randint(300, 900), 430 if dusk else 170), 52, "#fff1c9")
    draw = ImageDraw.Draw(img)
    _ridge(draw, rng, 470, 26, "#54456b" if dusk else "#5b8c7a", jagged=False)
    _water(draw, rng, 480, "#33507a" if dusk else "#2a9dbf", "#f6c89a" if dusk else "#d8f3fb")
    _ridge(draw, rng, 760, 22, "#d9b98a" if dusk else "#f1dcae", jagged=False)
    return img


def scene_mountains(rng: random.Random, snow: bool, evening: bool) -> Image.Image:
    img = _sky(["#41295a", "#d76d77", "#ffaf7b"] if evening else ["#2f6fb5", "#a9d4f2", "#eef6fb"])
    _glow(img, (rng.randint(200, 1000), 210), 44, "#fff6d8")
    draw = ImageDraw.Draw(img)
    far, mid, near = (
        ("#c9d6e6", "#e9eff6", "#ffffff") if snow
        else ("#6b5b7b", "#3f4a5e", "#22303c") if evening
        else ("#8aa6b8", "#4f7a68", "#2e5441")
    )
    _ridge(draw, rng, 430, 120, far, jagged=True)
    _ridge(draw, rng, 560, 90, mid, jagged=True)
    _ridge(draw, rng, 720, 40, near, jagged=False)
    if snow:
        for _ in range(26):  # Tannen
            x, y = rng.randint(0, WIDTH), rng.randint(650, 790)
            h = rng.randint(50, 100)
            draw.polygon([(x, y - h), (x - h // 3, y), (x + h // 3, y)], fill=_hex("#2c4a3e"))
    return img


def scene_city(rng: random.Random, fireworks: bool, river: bool) -> Image.Image:
    img = _sky(["#0b1026", "#1f2a52", "#47366b"] if fireworks else ["#23304f", "#6b5b8c", "#f0a17a"])
    draw = ImageDraw.Draw(img)
    _stars(draw, rng, 380, 120)
    if fireworks:
        for color in ("#ffd166", "#ef476f", "#7bdff2", "#c4f07a"):
            cx, cy = rng.randint(150, WIDTH - 150), rng.randint(90, 330)
            reach = rng.randint(70, 130)
            for k in range(28):
                ang = k / 28 * math.tau
                draw.line(
                    [(cx + math.cos(ang) * 14, cy + math.sin(ang) * 14),
                     (cx + math.cos(ang) * reach, cy + math.sin(ang) * reach)],
                    fill=_hex(color), width=3,
                )
    else:
        _glow(img, (rng.randint(250, 950), 300), 36, "#ffe9c4")
        draw = ImageDraw.Draw(img)
    _skyline(draw, rng, 620 if river else 700, "#141a2e", "#ffd98a")
    if river:
        _water(draw, rng, 640, "#1c2745", "#f0b27a")
    return img


def scene_concert(rng: random.Random, open_air: bool) -> Image.Image:
    img = _sky(["#1b2a4e", "#4b3f72", "#c9657a"] if open_air else ["#08060f", "#1a1030", "#2a1245"])
    if open_air:
        _stars(ImageDraw.Draw(img), rng, 300, 60)
    _beams(img, rng, ["#ff4d8d", "#5ad1ff", "#ffd23f", "#9b5de5"])
    draw = ImageDraw.Draw(img)
    draw.rectangle([180, 420, WIDTH - 180, 520], fill=_hex("#0d0a18"))
    _crowd(draw, rng, 640, "#05040a")
    return img


def scene_paris(rng: random.Random, morning: bool) -> Image.Image:
    img = _sky(["#f7c59f", "#f6e2c6", "#cfe3f2"] if morning else ["#141e3c", "#3d3f7a", "#e08f86"])
    draw = ImageDraw.Draw(img)
    if not morning:
        _stars(draw, rng, 300, 70)
    _glow(img, (240 if morning else 960, 250), 40, "#fff2cf")
    draw = ImageDraw.Draw(img)
    ink = "#4a4258" if morning else "#10132a"
    _tower(draw, 640, 640, 470, ink)
    _skyline(draw, rng, 690, ink, "#ffd98a", max_h=150)
    return img


def scene_dinner(rng: random.Random, accent: str) -> Image.Image:
    img = _sky(["#3b2a20", "#6e4a33", "#9c6b45"])
    _glow(img, (WIDTH // 2, 150), 60, "#ffcf87")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 260, WIDTH, HEIGHT], fill=_hex("#7a5236"))
    for y in range(270, HEIGHT, 58):  # Holzmaserung
        draw.line([(0, y), (WIDTH, y)], fill=_hex("#6b452c"), width=3)
    _table(draw, rng, accent)
    return img


SCENES = {
    "demo_mallorca_1.jpg": lambda r: scene_beach(r, dusk=True),
    "demo_mallorca_2.jpg": lambda r: scene_beach(r, dusk=False),
    "demo_amalfi_1.jpg": lambda r: scene_beach(r, dusk=False),
    "demo_allgaeu_1.jpg": lambda r: scene_mountains(r, snow=False, evening=False),
    "demo_allgaeu_2.jpg": lambda r: scene_mountains(r, snow=False, evening=True),
    "demo_ski_1.jpg": lambda r: scene_mountains(r, snow=True, evening=False),
    "demo_berlin_1.jpg": lambda r: scene_city(r, fireworks=True, river=False),
    "demo_wien_1.jpg": lambda r: scene_city(r, fireworks=False, river=True),
    "demo_konzert_1.jpg": lambda r: scene_concert(r, open_air=False),
    "demo_konzert_2.jpg": lambda r: scene_concert(r, open_air=True),
    "demo_paris_1.jpg": lambda r: scene_paris(r, morning=False),
    "demo_paris_2.jpg": lambda r: scene_paris(r, morning=True),
    "demo_dinner_1.jpg": lambda r: scene_dinner(r, accent="#b5443a"),
    "demo_dinner_2.jpg": lambda r: scene_dinner(r, accent="#e0b04f"),
}


def main() -> None:
    missing = set(demo_photo_filenames()) - set(SCENES)
    if missing:
        sys.exit(f"Keine Szene für: {', '.join(sorted(missing))}")

    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    for name, build in SCENES.items():
        # Seed aus dem Dateinamen: jeder Lauf erzeugt dieselben Bilder.
        img = build(random.Random(name))
        img.save(OUT_DIR / name, "JPEG", quality=82, optimize=True, progressive=True)

        thumb = img.copy()
        thumb.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
        stem, ext = os.path.splitext(name)
        thumb.save(THUMB_DIR / f"{stem}_thumb{ext}", "JPEG", quality=80, optimize=True)
        print(f"  {name}")
    print(f"{len(SCENES)} Bilder unter {OUT_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
