/* SIRAJ bundle entry — loaded by Frappe esbuild at bench build time.
 *
 * Imports are in the exact order hooks.py used to emit <script> tags so
 * dependencies are satisfied. siraj-record-meta defines window.sirajIcons
 * that later files read at eval-time; siraj-compat must load before any
 * code that touches Leaflet.
 */
import './siraj-record-meta.js';
import './siraj-map/siraj-map.js';
import './siraj-map/siraj-graph.js';
import './siraj-map/siraj-filters.js';
import './siraj-map-kit.js';
import './siraj-map-toolbar.js';
import './siraj-basemap.js';
import './siraj-map-advanced.js';
import './siraj-list-icons.js';
import './siraj-compat.js';
import './coordinate_map.js';
import './siraj-geo.js';
import './siraj-icons.js';
import './siraj-profile-fields.js';
