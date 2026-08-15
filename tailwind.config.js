/**
 * Tailwind-Konfiguration für den statischen CSS-Build.
 *
 * Ersetzt den früheren <script src="https://cdn.tailwindcss.com">-Einbau, der
 * das CSS bei jedem Seitenaufruf im Browser neu erzeugt hat. Bewusst
 * Tailwind 3.x: das ist die Version, die der CDN-Build ausgeliefert hat —
 * ein Sprung auf 4.x würde Defaults (Preflight, Farben, Schatten) ändern und
 * damit das Aussehen aller Templates.
 *
 * Neu generieren nach Template-Änderungen mit neuen Utility-Klassen:
 *   npx tailwindcss@3 -i static/css/tailwind-input.css \
 *       -o static/css/app.css --minify
 */
module.exports = {
  // static/js wird mitgescannt: pin-animation.js & timeline-sort.js setzen
  // Utility-Klassen per classList.add()/className zur Laufzeit.
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
