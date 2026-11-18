/* SIRAJ icon facade.
 *
 * Glyphs and colours are served from siraj-record-meta.js (loaded via
 * app_include_js so they're always present). This file exists so legacy
 * require('/assets/.../js/siraj-icons.js') calls keep working and so tests can
 * assert a single public entry point.
 */
document.createElement('siraj-icons');   // mark module loaded; nothing else to do.
