# 🌳 Memory Tree — Product Requirements Document

**Gemeinsames digitales Erinnerungsbuch für Paare**

Version 1.0 | Python Web-App | VS Code

---

## 1. Produktübersicht

### 1.1 Vision

Memory Tree ist eine private, passwortgeschützte Web-App für zwei Partner. Sie ermöglicht das gemeinsame Festhalten von Urlaubserinnerungen, Meilensteinen, Fotos und Erlebnissen — visuell aufbereitet als wachsender interaktiver Baum, der die Beziehungsgeschichte lebendig macht.

### 1.2 Projektsteckbrief

| Eigenschaft | Wert |
|---|---|
| Projektname | Memory Tree |
| Projekttyp | Privates Web-App-Projekt (lokal oder Self-Hosted) |
| Zielgruppe | 2 Personen (Paar, privat) |
| Technologie Backend | Python 3.11+ / FastAPI |
| Technologie Frontend | Jinja2, Tailwind CSS, Vanilla JS |
| Datenbank | SQLite mit SQLAlchemy ORM |
| Visualisierung | D3.js (Memory Tree), Leaflet.js (Karte) |
| Authentifizierung | 2-User-System (Partner A & B) |
| IDE | Visual Studio Code |
| Deployment | Lokal (Localhost) oder Raspberry Pi / VPS |

### 1.3 Problemstellung

Paare sammeln im Laufe der Zeit unzählige Erinnerungen in verschiedenen Apps, Fotogalerien und sozialen Medien. Es fehlt ein gemeinsamer, privater Ort, der diese Erinnerungen chronologisch, emotional und visuell vereint — mit persönlichem Bezug und ohne öffentliche Sichtbarkeit.

### 1.4 Lösungsansatz

- Ein privater, gemeinsamer digitaler Raum für 2 Nutzer
- Visualisierung als wachsender Baum – jede Erinnerung ist ein Ast/Knoten
- Chronologischer Zeitstrahl mit Beziehungsmeilensteinen
- Interaktive Weltkarte aller besuchten Orte
- Fotogalerie mit Filteroptionen
- Automatische Berechnung der Beziehungsdauer

---

## 2. Feature-Anforderungen

### 2.1 Authentifizierung & Nutzerverwaltung

#### 2.1.1 Login-System

- Zwei fest definierte Nutzerkonten: Partner A und Partner B
- JWT-basierte Session-Verwaltung
- Gemeinsames Passwort oder individuelle Credentials
- Automatischer Logout nach Inaktivität (konfigurierbar)

#### 2.1.2 Beziehungsprofil

- Einstellbares Beziehungsanfangsdatum („Zusammen seit...")
- Namen beider Partner anpassbar
- Profilbilder für beide Partner hochladbar

### 2.2 Erinnerungen (Core Feature)

#### 2.2.1 Erinnerung erstellen

- Pflichtfelder: Titel, Datum
- Optionale Felder: Beschreibung (Rich Text), Ort, GPS-Koordinaten, Stimmung (Emoji-Auswahl), Kategorie-Tags
- Mehrere Fotos pro Erinnerung hochladbar (JPEG, PNG, WEBP, max. 10 MB/Foto)
- Beide Partner können Erinnerungen erstellen und bearbeiten

#### 2.2.2 Kategorien & Tags

| Kategorie | Beispiele |
|---|---|
| 🏖️ Urlaub | Reisen, Ausflüge, Trips |
| 🌟 Meilenstein | Erstes Date, Erstes gemeinsames Zuhause, Verlobung |
| 🎉 Feier | Geburtstage, Jubiläen, Silvester |
| 📸 Alltag | Besondere Momente im Alltag |
| 🌯 Abenteuer | Aktivitäten, Sport, Erlebnisse |
| ❤️ Besonderes | Romantische Momente, Überraschungen |

### 2.3 Memory Tree Visualisierung

Das Herzstück der App. Ein interaktiver Baum (D3.js), dessen Struktur und Größe mit jeder Erinnerung wächst.

- Jede Erinnerung = ein Knoten/Blatt am Baum
- Kategorien bilden eigene Äste
- Knoten anklickbar: Öffnet eine Detail-Karte mit Bild, Beschreibung, Datum
- Hover-Effekt zeigt Vorschau
- Animiertes Wachstum beim Hinzufügen neuer Erinnerungen
- Filterbar nach Jahr und Kategorie

### 2.4 Zeitstrahl

- Horizontaler / vertikaler Timeline-View aller Erinnerungen
- Automatische Berechnung: „Ihr seid seit X Jahren, Y Monaten und Z Tagen zusammen"
- Meilensteine hervorgehoben (Icon + farblicher Akzent)
- Jubiläums-Countdown: „In X Tagen ist euer 3. Jahrestag"
- Filterbar nach Jahr

### 2.5 Meilensteine

- Eigene Sektion für besondere Ereignisse
- Icon-Auswahl (Emoji oder Symbol)
- Felder: Titel, Datum, Beschreibung, Icon
- Hervorgehobene Darstellung im Zeitstrahl und Memory Tree

### 2.6 Reisekarte

- Interaktive Weltkarte via Leaflet.js
- Pins für jeden besuchten Ort
- Klick auf Pin: zeigt zugehörige Erinnerungen
- Statistik: Anzahl Orte, Länder, Kontinente
- Heatmap-Option für häufig besuchte Orte

### 2.7 Fotogalerie

- Grid-Layout aller hochgeladenen Fotos
- Filterbar nach: Jahr, Kategorie, Ort
- Lightbox-Ansicht mit Navigation
- Download einzelner Fotos

### 2.8 Dashboard (Startseite)

- Begrüßung „Ihr seid seit X Tagen zusammen"
- Letzte Erinnerungen (3–5 Vorschaukarten)
- Anstehende Jubiläen / Meilensteine
- Statistik-Widgets: Anzahl Erinnerungen, Fotos, besuchte Länder
- Zufalls-Erinnerung: „Heute vor 2 Jahren..."

---

## 3. Technische Spezifikation

### 3.1 Projektstruktur

```
memory-tree/
├── main.py                  # FastAPI App-Einstiegspunkt
├── models.py                # SQLAlchemy Datenmodelle
├── database.py              # DB-Verbindung & Session
├── auth.py                  # JWT-Auth & Middleware
├── config.py                # App-Konfiguration
├── routers/
│   ├── memories.py          # CRUD Erinnerungen
│   ├── milestones.py        # Meilensteine
│   ├── photos.py            # Foto-Upload & Verwaltung
│   ├── map.py               # Geodaten & Orte
│   └── auth.py              # Login/Logout Routes
├── static/
│   ├── uploads/             # Hochgeladene Bilder
│   ├── css/tailwind.css
│   ├── js/
│   │   ├── tree.js          # D3.js Memory Tree
│   │   ├── map.js           # Leaflet.js Karte
│   │   └── gallery.js       # Galerie & Lightbox
│   └── img/                 # App-Assets
├── templates/
│   ├── base.html            # Basis-Layout
│   ├── dashboard.html
│   ├── tree.html            # Memory Tree
│   ├── timeline.html        # Zeitstrahl
│   ├── milestones.html
│   ├── map.html
│   ├── gallery.html
│   ├── memory_detail.html
│   ├── memory_form.html
│   └── settings.html
├── requirements.txt
├── .env                     # Secrets (nicht committen!)
└── README.md
```

### 3.2 Datenmodelle

| Tabelle | Wichtigste Felder |
|---|---|
| users | id, name, username, password_hash, avatar_path, partner_since |
| memories | id, title, date, description, location, lat, lng, mood, category, created_by |
| photos | id, memory_id, filepath, caption, uploaded_at |
| milestones | id, title, date, icon, description, is_anniversary |
| places | id, memory_id, name, country, lat, lng |

### 3.3 API-Routen (Übersicht)

| Method + Route | Beschreibung |
|---|---|
| POST /auth/login | Login, gibt JWT zurück |
| GET /memories | Alle Erinnerungen (gefiltert) |
| POST /memories | Neue Erinnerung erstellen |
| GET /memories/{id} | Einzelne Erinnerung |
| PUT /memories/{id} | Erinnerung bearbeiten |
| DELETE /memories/{id} | Erinnerung löschen |
| POST /memories/{id}/photos | Foto hochladen |
| GET /milestones | Alle Meilensteine |
| POST /milestones | Meilenstein erstellen |
| GET /map/places | Alle Orte für Karte |
| GET /stats | Dashboard-Statistiken |

### 3.4 Technologie-Versionen

| Paket | Version |
|---|---|
| Python | 3.11+ |
| FastAPI | 0.111+ |
| SQLAlchemy | 2.0+ |
| Uvicorn | 0.29+ |
| python-jose (JWT) | 3.3+ |
| Passlib (bcrypt) | 1.7+ |
| Pillow (Bildverarbeitung) | 10+ |
| D3.js | 7.x (CDN) |
| Leaflet.js | 1.9.x (CDN) |
| Tailwind CSS | 3.x (CDN oder CLI) |

---

## 4. Entwicklungs-Roadmap

| Phase | Inhalt & Deliverables |
|---|---|
| Phase 1 – Fundament (Woche 1–2) | FastAPI Setup, SQLite DB, Auth-System (Login/Logout), Basis-Templates, requirements.txt |
| Phase 2 – Erinnerungen (Woche 3–4) | CRUD Erinnerungen, Foto-Upload, Detailansicht, Formular-Validierung |
| Phase 3 – Zeitstrahl & Meilensteine (Woche 5) | Timeline-View, Beziehungsdauer-Berechnung, Meilenstein-Verwaltung, Jubiläums-Countdown |
| Phase 4 – Memory Tree (Woche 6–7) | D3.js Baum-Visualisierung, Knoten-Interaktion, Kategorie-Äste, Animationen |
| Phase 5 – Karte & Galerie (Woche 8) | Leaflet.js Reisekarte, Pins & Popups, Fotogalerie, Lightbox, Filter |
| Phase 6 – Dashboard & Polish (Woche 9–10) | Dashboard-Widgets, Mobile Responsiveness, Feinschliff, Fehlerbehandlung, README |

---

## 5. Nicht-funktionale Anforderungen

### 5.1 Sicherheit

- Alle Endpunkte (außer /login) erfordern gültiges JWT
- Passwörter werden mit bcrypt gehasht gespeichert
- Upload-Dateien werden auf Typ und Größe validiert
- .env für Secrets (SECRET_KEY, Datenbankpfad)

### 5.2 Performance

- Startzeit der App < 3 Sekunden
- Seitenlade-Zeit < 1 Sekunde (ohne Bilder)
- Bilder werden beim Upload automatisch auf max. 1920px skaliert

### 5.3 Usability

- Vollständig responsiv (Mobile & Desktop)
- Intuitive Navigation ohne Dokumentation
- Deutschsprachige Oberfläche

---

## 6. Definition of Done

- [ ] Alle Seiten laden ohne 500-Fehler
- [ ] Login funktioniert für beide Partner
- [ ] Erinnerungen können erstellt, bearbeitet und gelöscht werden
- [ ] Fotos können hochgeladen und angezeigt werden
- [ ] Memory Tree zeigt alle Erinnerungen als Knoten
- [ ] Zeitstrahl zeigt korrekte Beziehungsdauer
- [ ] Reisekarte zeigt Pins aller gespeicherten Orte
- [ ] App ist auf Mobilgeräten benutzbar
- [ ] README mit Installationsanleitung vorhanden
