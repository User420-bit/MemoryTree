#!/usr/bin/env python3
"""
Übernimmt fertige Fotos als Demo-Bilder des Gastzugangs nach static/demo/.

Erwartet einen Ordner mit Quelldateien, benannt wie die Dateinamen aus demo_data.py
(gleicher Stamm, Endung png/jpg/jpeg/webp — z. B. ``demo_paris_1.png``). Jedes
Bild wird mittig auf 3:2 beschnitten, auf 1200×800 gebracht und als JPEG neu
kodiert; Metadaten der Quelle (EXIF, Prompt-Chunks) gehen dabei verloren. Das
Thumbnail folgt der Konvention aus uploads.thumbnail_ref().

Galerie und Baum zeigen quadratische Ausschnitte (object-cover) — das Motiv
sollte also in der Bildmitte sitzen.

Die aktuellen Bilder sind KI-generiert (Higgsfield, Modell ``nano_banana``):
bewusst als unperfekte Handyfotos angelegt und ohne erkennbare Gesichter, weil
es "Lena & Max" nicht gibt. Nur Bilder verwenden, die öffentlich sein dürfen —
/static/ ist ohne Login abrufbar.

Nutzung:
    python3 scripts/import_demo_photos.py <quellordner>

Das Ergebnis wird committet; das Skript läuft nicht beim Deploy.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageOps

from demo_data import demo_photo_filenames
from make_demo_images import HEIGHT, OUT_DIR, ROOT, WIDTH, save_with_thumb

SOURCE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def find_source(folder: Path, name: str) -> Path | None:
    stem = os.path.splitext(name)[0]
    for ext in SOURCE_EXTENSIONS:
        candidate = folder / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip())
    folder = Path(sys.argv[1]).expanduser()
    if not folder.is_dir():
        sys.exit(f"Kein Ordner: {folder}")

    missing: list[str] = []
    for name in demo_photo_filenames():
        source = find_source(folder, name)
        if source is None:
            missing.append(name)
            continue
        with Image.open(source) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")
        img = ImageOps.fit(img, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        save_with_thumb(img, name)
        print(f"  {name}  <-  {source.name}")

    # Ein Ordner mit nur einem Teil der Bilder ist der Normalfall (ein Foto
    # austauschen) — Fehler ist erst, wenn gar nichts gepasst hat.
    imported = len(demo_photo_filenames()) - len(missing)
    if not imported:
        sys.exit(f"Keine passende Quelldatei in {folder} (erwartet z. B. {missing[0]})")
    if missing:
        print(f"  unverändert: {', '.join(missing)}")
    print(f"{imported} Bilder unter {OUT_DIR.relative_to(ROOT)}/ geschrieben")


if __name__ == "__main__":
    main()
