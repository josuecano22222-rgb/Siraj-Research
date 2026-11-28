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
		// Standard admin-field names so the live cascade also covers custom
		// DocTypes that use the conventional field group but have no boot
		// registry entry (the backend resolves them via build_cfg_from_meta).
		const standardAdminFields = {
			country: 'country', governorate: 'governorate', district: 'district',
			municipality: 'municipality', village: 'village', community: 'community',
			place_name: 'place_name',
		};
		return Object.assign({
			lat_field: 'latitude',
			lon_field: 'longitude',
			map_field: 'geo_point',
			origin_confirmed_field: 'coordinate_origin_confirmed',
			uncertainty_field: 'geo_uncertainty_m',
			admin_fields: standardAdminFields,
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

	/* Location-selection cascade: when a linked Place is picked, fetch its
	 * coordinates and resolve the full hierarchy from them — so selecting a
	 * location auto-populates country/province/city just like typing
	 * coordinates. */
	async function resolveFromPlace(frm, cfg) {
		const linkedField = cfg.linked_place_field;
		if (!linkedField) return;
		const placeName = frm.doc && frm.doc[linkedField];
		if (!placeName) return;
		const df = field(frm, linkedField);
		const placeDoctype = (df && df.df && df.df.options) || 'Place';
		try {
			const values = await frappe.db.get_value(
				placeDoctype, placeName, ['latitude', 'longitude']
			);
			if (!values || values.latitude == null || values.longitude == null) return;
			await guarded(frm, async () => {
				try {
					await frm.set_value({
						[cfg.lat_field]: values.latitude,
						[cfg.lon_field]: values.longitude,
					});
				} catch (_) { /* keep the selection even if coord copy fails */ }
			});
			await showHierarchy(frm, cfg, values.latitude, values.longitude);
		} catch (_) { /* never block the form on a place cascade */ }
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

	// The enhanced SIRAJ map is mounted inside the Geolocation field, so the
	// stock Leaflet map must not initialise at all. Frappe's Geolocation
	// control assumes its Leaflet.Draw and Locate plugins are present; on
	// this bench they are not always loaded at form-render time, which threw
	// `L.Control.Draw is not a constructor` and could abort form refresh.
	// Suppress only our `geo_point` fields; other Geolocation fields keep
	// Frappe's native behaviour.
	function suppressStockGeoPointMap() {
		const C = frappe.ui.form && frappe.ui.form.ControlGeolocation;
		if (!C || C._sirajQuietMap || !C.prototype.make_map) return false;
		const original = C.prototype.make_map;
		C.prototype.make_map = function (value) {
			if (this.df && this.df.fieldname === 'geo_point') return;
			return original.call(this, value);
		};
		C._sirajQuietMap = true;
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
		if (cfg.linked_place_field) {
			handlers[cfg.linked_place_field] = (frm) => resolveFromPlace(frm, cfg);
		}
		frappe.ui.form.on(doctype, handlers);
	}

	function boot() {
		suppressStockGeoPointMap();
		const docs = window.sirajCoordinateDocs || {};
		Object.keys(docs).forEach(doctype => register(doctype, configFor(doctype)));
		// Generic fallback covers custom DocTypes that use our standard field
		// names but have no entry in the boot registry.
		$(document).on('form-refresh.sirajGeopoint', (_event, frm) => {
			suppressStockGeoPointMap();
			if (!frm || !frm.doctype) return;
			const cfg = configFor(frm.doctype);
			register(frm.doctype, cfg);
			attach(frm, cfg);
		});
	}

	window.SirajGeoPoint = {
		configFor, fromMap, toMap, attach, resolveFromPlace,
		firstPoint: () => core() && core().firstPoint,
	};
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
	else boot();
})();
