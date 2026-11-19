/* Bridge Frappe's native Geolocation ("map") field to SIRAJ coordinates.
 *
 * Frappe renders a Geolocation control as a Leaflet map and stores a GeoJSON
 * FeatureCollection. SIRAJ research forms use separate latitude/longitude
 * fields (historic Float fields, target Data fields) plus six administrative
 * hierarchy links. This module keeps all three representations in sync:
 *
 *   map point -> latitude/longitude -> hierarchy
 *   latitude/longitude -> map point
 *
 * A native map field is used when present, so the picker is a real DocType
 * field and no longer depends on an injected wrapper surviving a Frappe
 * layout change. The older injected map (coordinate_map.js) remains the
 * fallback for DocTypes without a Geolocation field.
 */
(() => {
	'use strict';

	const t = s => (typeof __ === 'function' ? __(s) : s);
	const registered = new Set();
	const core = () => window.SirajGeoPointCore;

	function configFor(doctype) {
		const fromBoot = (window.sirajCoordinateDocs && window.sirajCoordinateDocs[doctype]) || {};
		return Object.assign({
			lat_field: 'latitude',
			lon_field: 'longitude',
			map_field: 'geo_point',
			origin_confirmed_field: 'coordinate_origin_confirmed',
			uncertainty_field: 'geo_uncertainty_m',
			admin_fields: {},
		}, fromBoot);
	}

	function field(frm, name) {
		return frm && frm.fields_dict && frm.fields_dict[name];
	}

	function writable(frm, name) {
		const control = field(frm, name);
		return !!(control && typeof control.get_status === 'function' && control.get_status() === 'Write');
	}

	function originConfirmed(frm, cfg) {
		const value = frm && frm.doc && frm.doc[cfg.origin_confirmed_field];
		return value === 1 || value === '1' || value === true;
	}

	function status(control, message, warning) {
		if (!control || !control.$wrapper) return;
		let $status = control.$wrapper.find('.siraj-geopoint-status');
		if (!$status.length) {
			$status = $('<div class="siraj-geopoint-status" role="status" aria-live="polite"></div>')
				.appendTo(control.$wrapper);
		}
		$status.text(message || '').toggleClass('is-warning', !!warning);
	}

	async function guarded(frm, work) {
		if (frm.flags && frm.flags.siraj_geo_sync) return;
		frm.flags = frm.flags || {};
		frm.flags.siraj_geo_sync = true;
		try { await work(); }
		finally { setTimeout(() => { frm.flags.siraj_geo_sync = false; }, 0); }
	}

	async function showHierarchy(frm, cfg, lat, lon) {
		// Old path still fills empty Link/Data fields with a diff-aware
		// Keep/Replace dialog; the shared UI renders the complete chain and
		// provenance below the fields.
		try {
			if (window.SirajCoordinateMap && window.SirajCoordinateMap.resolveAndApply) {
				window.SirajCoordinateMap.resolveAndApply(frm, cfg, lat, lon);
			}
		} catch (_) { /* hierarchy is an enhancement, never a save blocker */ }
		try {
			if (window.SirajHierarchy && window.SirajHierarchy.refreshForm) {
				await window.SirajHierarchy.refreshForm(frm, cfg, lat, lon, { force: true });
			}
		} catch (_) { /* display failure must not undo coordinates */ }
	}

	async function fromMap(frm, cfg) {
		if (frm.flags && frm.flags.siraj_custom_map) return;  // enhanced map owns the field
		const helpers = core();
		if (!helpers) return;
		const raw = frm.doc && frm.doc[cfg.map_field];
		const picked = helpers.firstPoint(raw);
		if (!picked) return;
		if (helpers.isZero(picked.lat, picked.lon) && !originConfirmed(frm, cfg)) {
			status(field(frm, cfg.map_field), t('Coordinates are exactly (0,0). Confirm that this is a real point.'), true);
			return;
		}
		const values = {
			[cfg.lat_field]: String(picked.lat),
			[cfg.lon_field]: String(picked.lon),
		};
		if (helpers.isZero(picked.lat, picked.lon) && writable(frm, cfg.origin_confirmed_field)) {
			values[cfg.origin_confirmed_field] = 1;
		}
		if (writable(frm, 'geocoding_method')) values.geocoding_method = 'map_pick';
		if (writable(frm, 'geometry_source') && !(frm.doc && frm.doc.geometry_source)) {
			values.geometry_source = 'map_pick';
		}
		await guarded(frm, async () => {
			try {
				await frm.set_value(values);
				status(field(frm, cfg.map_field), t('Coordinates and hierarchy updated from the map.'));
			} catch (_) {
				status(field(frm, cfg.map_field), t('Could not update the coordinate fields.'), true);
			}
		});
		await showHierarchy(frm, cfg, picked.lat, picked.lon);
	}

	async function toMap(frm, cfg) {
		if (frm.flags && frm.flags.siraj_custom_map) return;  // enhanced map owns the field
		const helpers = core();
		if (!helpers) return;
		const lat = helpers.latitude(frm.doc && frm.doc[cfg.lat_field]);
		const lon = helpers.longitude(frm.doc && frm.doc[cfg.lon_field]);
		if (lat === null || lon === null) return;
		if (helpers.isZero(lat, lon) && !originConfirmed(frm, cfg)) {
			status(field(frm, cfg.map_field), t('Coordinates are exactly (0,0). No marker is shown until you confirm it is real.'), true);
			return;
		}
		const encoded = helpers.encode(lat, lon, { source: 'siraj_coordinate_fields' });
		if (!encoded) return;
		if ((frm.doc && frm.doc[cfg.map_field]) === encoded) return;
		if (!writable(frm, cfg.map_field)) return;
		await guarded(frm, async () => {
			try { await frm.set_value(cfg.map_field, encoded); }
			catch (_) { /* keep typed coordinates even if map sync fails */ }
		});
		await showHierarchy(frm, cfg, lat, lon);
	}

	// Keep our map field a point picker. Frappe's stock Geolocation control
	// also offers polygons, lines and circles, which cannot be represented by
	// latitude/longitude and would be silently lost by the mirror. Other apps'
	// Geolocation fields keep their native controls.
	function installPointOnlyControl() {
		const C = frappe.ui.form && frappe.ui.form.ControlGeolocation;
		if (!C || C._sirajPointOnly || !C.prototype.get_leaflet_controls) return false;
		const original = C.prototype.get_leaflet_controls;
		C.prototype.get_leaflet_controls = function () {
			if (!this.df || this.df.fieldname !== 'geo_point') return original.call(this);
			return new L.Control.Draw({
				position: 'topleft',
				draw: {
					marker: true, polyline: false, polygon: false,
					circle: false, rectangle: false, circlemarker: false,
				},
				edit: { featureGroup: this.editableLayers, remove: true },
			});
		};
		C._sirajPointOnly = true;
		return true;
	}

	function attach(frm, cfg) {
		if (frm.flags && frm.flags.siraj_custom_map) return;  // enhanced map owns the field
		const control = field(frm, cfg.map_field);
		if (!control || !control.df || control.df.fieldtype !== 'Geolocation') return;
		if (control.$wrapper) control.$wrapper.attr('data-siraj-geopoint', '1');
		const map = control.map;
		if (map && !map._sirajGeopointBound) {
			map._sirajGeopointBound = true;
			// Frappe's control writes the FeatureCollection before these
			// events finish; the field handler is the single source of truth.
			map.on('draw:created draw:edited', () => setTimeout(() => fromMap(frm, cfg), 0));
			map.on('draw:deleted', () => setTimeout(() => fromMap(frm, cfg), 0));
		}
		if (!(frm.doc && frm.doc[cfg.map_field])) toMap(frm, cfg);
	}

	function register(doctype, cfg) {
		if (!frappe.ui.form || !frappe.ui.form.on) return false;
		if (registered.has(doctype)) return;
		registered.add(doctype);
		const handlers = {
			setup(frm) { attach(frm, cfg); },
			refresh(frm) { attach(frm, cfg); },
			[cfg.map_field](frm) { fromMap(frm, cfg); },
			[cfg.lat_field](frm) { toMap(frm, cfg); },
			[cfg.lon_field](frm) { toMap(frm, cfg); },
			[cfg.origin_confirmed_field](frm) { toMap(frm, cfg); },
		};
		frappe.ui.form.on(doctype, handlers);
	}

	function boot() {
		installPointOnlyControl();
		const docs = window.sirajCoordinateDocs || {};
		Object.keys(docs).forEach(doctype => register(doctype, configFor(doctype)));
		// Generic fallback covers custom DocTypes that use our standard field
		// names but have no entry in the boot registry.
		$(document).on('form-refresh.sirajGeopoint', (_event, frm) => {
			installPointOnlyControl();
			if (!frm || !frm.doctype) return;
			const cfg = configFor(frm.doctype);
			register(frm.doctype, cfg);
			attach(frm, cfg);
		});
	}

	window.SirajGeoPoint = { configFor, fromMap, toMap, attach, firstPoint: () => core() && core().firstPoint };
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
	else boot();
})();
