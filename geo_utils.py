"""Offline-Länder-Erkennung per Bounding Box.

Keine externen Dependencies, keine Netzwerkaufrufe. Deckt die gängigsten
Reiseziele ab. Bei unbekannten Koordinaten wird `None` zurückgegeben
(nicht `"Unbekannt"`), damit die aufrufende Logik entscheiden kann.

Bounding-Boxes sind grob approximiert — für eine Paar-App mit
überschaubarer Zahl an Erinnerungen ausreichend. Reihenfolge in der
Tabelle: kleinere/spezifischere Länder zuerst, damit sie vor größeren
matchen (z. B. Monaco vor Frankreich).
"""

from __future__ import annotations

# Tuple-Struktur: (min_lat, min_lng, max_lat, max_lng, name_de)
_COUNTRY_BBOXES: tuple[tuple[float, float, float, float, str], ...] = (
    # Mitteleuropa
    (47.270, 9.530, 55.060, 15.040, "Deutschland"),
    (46.370, 9.530, 49.020, 17.160, "Österreich"),
    (45.820, 5.960, 47.810, 10.490, "Schweiz"),
    (49.450, 5.740, 50.180, 6.530, "Luxemburg"),
    (50.750, 2.540, 51.510, 6.410, "Belgien"),
    (50.750, 3.360, 53.550, 7.230, "Niederlande"),
    (49.000, 14.070, 51.060, 18.870, "Tschechien"),
    (47.730, 16.830, 49.600, 22.570, "Slowakei"),
    (45.740, 16.100, 48.580, 22.900, "Ungarn"),
    (49.000, 14.120, 54.840, 24.150, "Polen"),
    # Nordeuropa
    (54.560, 8.070, 57.750, 12.690, "Dänemark"),
    (55.340, 10.960, 69.060, 24.170, "Schweden"),
    (57.960, 4.650, 71.190, 31.060, "Norwegen"),
    (59.810, 20.550, 70.090, 31.590, "Finnland"),
    (63.400, -24.540, 66.540, -13.500, "Island"),
    # Westeuropa
    (49.850, -6.420, 58.640, 1.770, "Vereinigtes Königreich"),
    (51.420, -10.480, 55.390, -5.980, "Irland"),
    (41.330, -5.140, 51.090, 9.560, "Frankreich"),
    (43.720, 7.400, 43.760, 7.440, "Monaco"),
    # Südeuropa
    (35.290, 6.600, 47.090, 18.520, "Italien"),
    (36.000, -9.560, 43.790, 4.330, "Spanien"),
    (36.960, -9.530, 42.150, -6.190, "Portugal"),
    (34.570, 19.370, 41.750, 29.650, "Griechenland"),
    (45.420, 13.370, 46.880, 16.610, "Slowenien"),
    (42.380, 13.380, 46.550, 19.440, "Kroatien"),
    # Osteuropa
    (43.620, 22.360, 48.270, 29.700, "Rumänien"),
    (41.240, 22.360, 44.220, 28.610, "Bulgarien"),
    (35.820, 25.730, 42.100, 44.820, "Türkei"),
    # Amerika
    (24.520, -124.770, 49.380, -66.950, "USA"),
    (41.680, -141.000, 69.650, -52.620, "Kanada"),
    (14.530, -118.370, 32.720, -86.700, "Mexiko"),
    # Asien
    (20.220, 122.930, 45.520, 153.990, "Japan"),
    (33.190, 124.610, 38.620, 130.930, "Südkorea"),
    (8.720, 97.340, 20.460, 105.640, "Thailand"),
    (-11.010, 95.010, 6.080, 141.020, "Indonesien"),
    (1.160, 103.610, 1.470, 104.040, "Singapur"),
    (-44.950, 166.420, -34.100, 178.540, "Neuseeland"),
    (-43.650, 112.920, -10.690, 153.640, "Australien"),
    # Afrika
    (30.800, -9.760, 35.930, -1.060, "Marokko"),
    (22.000, 24.700, 31.670, 36.900, "Ägypten"),
    (-34.840, 16.460, -22.130, 32.890, "Südafrika"),
)


def country_from_coords(lat: float | None, lng: float | None) -> str | None:
    """Gibt den deutschen Ländernamen für die Koordinaten zurück.

    Returns None wenn `lat`/`lng` fehlen oder in keiner bekannten BBox liegen.
    Bei Überlappungen gewinnt der erste Treffer — kleinere Länder sind
    bewusst zuerst gelistet (siehe Modul-Docstring).
    """
    if lat is None or lng is None:
        return None
    for min_lat, min_lng, max_lat, max_lng, name in _COUNTRY_BBOXES:
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            return name
    return None
