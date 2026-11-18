/* Per-DocType coordinate map editor.
 *
 * Every DocType declared in window.sirajCoordinateDocs (populated from
 * record_icons.COORDINATE_DOCS on the server) gets one shared editor mounted
 * INSIDE the Position section, right after the longitude field. Any DocType
 * that exposes latitude/longitude Float/Data fields but is NOT in the config
 * still gets the editor (graceful fallback) so custom DocTypes work.
 *
 * The editor is a real form field: clicking/dragging calls frm.set_value so
 * the form shows "Not Saved", typing in the fields moves the pin, swapped
 * lat/lon and null-island (0,0) are flagged, read-only/permissions are
 * honoured, the toolbar comes from the shared SirajMapKit/TOOL_SPEC, and
 * layout changes (tab/section show, collapse) invalidate Leaflet size.
 *
 * data-siraj-build on the wrapper lets a screenshot show which build the DOM
 * was created by; Diagnostics reads it to verify executed-vs-server match.
 */
(() => {
	'use strict';

	const MODULE_VERSION = 3;

	// DocType → editor config. Merged over window.sirajCoordinateDocs (which
	// comes from the server via boot_session) so tests/print views that lack
	// boot metadata still have the correct per-doctype mapping.
	// admin_fields maps server-returned chain keys (from geo_resolve) to the
	// DocType's Link/Data fields that should receive them. Fields not present
	// on the form are silently skipped. `write_mode` controls auto-fill
	// behaviour: 'link' writes Link fields to Place/Governorate/... docs,
	// 'text' writes Data fields like place_name/community.
	const DEFAULT_COORDS = {
		'Person':                 { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'birthplace',   silhouette:'bust',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', community:'community', place_name:'place_name' } },
		'Institution':            { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'place',         silhouette:'building',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', community:'community', place_name:'place_name' } },
		'Place':                  { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'parent_place',  silhouette:'pin',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', community:'community' } },
		'Research Event':         { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'place',         silhouette:'star',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', community:'community', place_name:'place_name' } },
		'Military Unit':          { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'linked_place',  silhouette:'shield',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality' } },
		'Operational Deployment': { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:null,            silhouette:'crosshair',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', place_name:'location' } },
	};
	function docConfig(doctype) {
		const fromBoot = (window.sirajCoordinateDocs && window.sirajCoordinateDocs[doctype]) || {};
		return Object.assign({
			lat_field: 'latitude', lon_field: 'longitude',
			uncertainty_field: 'geo_uncertainty_m', linked_place_field: null,
			silhouette: 'pin',
		}, DEFAULT_COORDS[doctype] || {}, fromBoot);
	}

	// Incrementing id so multiple forms on one page (e.g. quick-entry dialog
	// over a detail view) do not collide.
	let instanceCounter = 0;
	const states = new Map();   // key: frm+cfg+docname  (handles multi-map)
	const registered = new Set();
	const t = s => (typeof __ === 'function' ? __(s) : s);

	// Fieldtypes we can read/write numbers from/into.
	const writableFieldTypes = new Set(['Data','Small Text','Text','Long Text','Float','Int','Currency','Percent']);
	const readableFieldTypes = new Set([...writableFieldTypes, 'Read Only']);

	let assetsPromise;
	const assets = () => {
		if (!assetsPromise) {
			assetsPromise = Promise.resolve(frappe.require([
				'/assets/siraj_research/vendor/leaflet/leaflet.css',
				'/assets/siraj_research/vendor/leaflet/leaflet.js',
				'/assets/siraj_research/vendor/topojson/topojson-client.min.js',
			])).then(() => {
				// siraj-map-toolbar.js installs itself after Leaflet appears;
				// wait for both SirajMapKit and the toolbar control so mount()
				// never sees L.control.sirajToolbar === undefined.
				return new Promise(res => {
					const check = () => (window.SirajMapKit && window.L && window.L.control && window.L.control.sirajToolbar) ? res() : setTimeout(check, 30);
					check();
				});
			}).catch(err => { assetsPromise = null; throw err; });
		}
		return assetsPromise;
	};

	/* ------- Coordinate parsing (Float, eastern-arabic, scientific notation) ------- */
	const EASTERN_DIGITS = /[٠-٩]/g;
	const PERSIAN_DIGITS = /[۰-۹]/g;
	function parseCoordinate(value, max) {
		if (value === undefined || value === null || typeof value === 'boolean') return null;
		if (typeof value === 'number') return Number.isFinite(value) && Math.abs(value) <= max ? value : null;
		const normalized = String(value).trim()
			.replace(EASTERN_DIGITS, c => String(c.charCodeAt(0) - 0x660))
			.replace(PERSIAN_DIGITS, c => String(c.charCodeAt(0) - 0x6f0))
			.replace(/٫/g, '.');
		if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(e[+-]?\d+)?$/i.test(normalized)) return null;
		const n = Number(normalized);
		if (!Number.isFinite(n) || Math.abs(n) > max) return null;
		return n;
	}
	function decimalText(number) {
		const text = String(number);
		if (!/[eE]/.test(text)) return text;
		const [c, e] = text.toLowerCase().split('e');
		const neg = c.startsWith('-');
		const u = c.replace(/^-/, '');
		const [w, f = ''] = u.split('.');
		const digits = w + f, pos = w.length + Number(e);
		const r = pos <= 0 ? '0.' + '0'.repeat(-pos) + digits
			: pos >= digits.length ? digits + '0'.repeat(pos - digits.length)
			: digits.slice(0, pos) + '.' + digits.slice(pos);
		return (neg ? '-' : '') + r;
	}

	function stateKey(frm, cfg) {
		return frm.doctype + '::' + (frm.docname || 'new') + '::' + cfg.lat_field + '::' + cfg.lon_field;
	}

	function controlsFor(frm, cfg) {
		const fields = frm.fields_dict || {};
		const lat = fields[cfg.lat_field], lon = fields[cfg.lon_field];
		if (!lat || !lon || typeof lat.get_status !== 'function' || typeof lon.get_status !== 'function') return null;
		const a = lat.get_status(), b = lon.get_status();
		if (a === 'None' || b === 'None') return null;
		if (!readableFieldTypes.has(lat.df.fieldtype) || !readableFieldTypes.has(lon.df.fieldtype)) return null;
		return {
			cfg, lat, lon,
			editable: a === 'Write' && b === 'Write'
				&& writableFieldTypes.has(lat.df.fieldtype)
				&& writableFieldTypes.has(lon.df.fieldtype),
		};
	}

	function currentValue(field, doc, name) {
		if (field.get_status() === 'Write' && field.$input && field.$input.length) return field.$input.val();
		return doc[name];
	}

	function removeState(state) {
		if (!state) return;
		state.lat.$input?.off('.sirajCoordinates');
		state.lon.$input?.off('.sirajCoordinates');
		if (state.tabObserver) { state.tabObserver.disconnect(); state.tabObserver = null; }
		if (state.sectionObserver) { state.sectionObserver.disconnect(); state.sectionObserver = null; }
		if (state.resizeObserver) { state.resizeObserver.disconnect(); state.resizeObserver = null; }
		if (state.measure) { try { state.measure.deactivate(); } catch (_) {} }
		if (state.uncertaintyCircle) { try { state.map.removeLayer(state.uncertaintyCircle); } catch (_) {} state.uncertaintyCircle = null; }
		if (state.ghostMarker)    { try { state.map.removeLayer(state.ghostMarker); }    catch (_) {} state.ghostMarker = null; }
		if (state.marker)         { try { state.map.removeLayer(state.marker); }         catch (_) {} state.marker = null; }
		if (state.map && !state.map._sirajRemoved) { try { state.map.remove(); state.map._sirajRemoved = true; } catch (_) {} }
		if (state.group && state.group[0] && state.group[0].parentNode) state.group.remove();
		states.delete(state.key);
	}

	function drawUncertainty(state, lat, lon) {
		if (state.uncertaintyCircle) { try { state.map.removeLayer(state.uncertaintyCircle); } catch (_) {} state.uncertaintyCircle = null; }
		const r = Number(state.frm && state.frm.doc && state.frm.doc[state.cfg.uncertainty_field]);
		if (!Number.isFinite(r) || r <= 0) return;
		const c = (window.sirajColours && window.sirajColours[state.frm.doctype]) || '#267b77';
		state.uncertaintyCircle = L.circle([lat, lon], {
			radius: r, color: c, weight: 1, opacity: 0.7, fillColor: c, fillOpacity: 0.08,
			dashArray: '4 3', interactive: false,
		}).addTo(state.map);
	}

	function pinIcon(doctype, color, size) {
		const s = size || 34;
		const h = Math.round(s * 1.15);
		return L.divIcon({
			className: 'sx-pin-wrapper',
			iconSize: [s, h],
			iconAnchor: [s/2, h],   // tip anchored to the clicked coordinate
			popupAnchor: [0, -Math.round(s*0.8)],
			tooltipAnchor: [0, -Math.round(s*0.5)],
			html: (window.sirajIcons && window.sirajIcons.pin) ? window.sirajIcons.pin(doctype || 'Place', color, s, {
				state: 'active',
				halo: false,
				ring: color || '#267b77',
				dot: false,
			}) : '',
		});
	}

	function ghostIcon(color) {
		// Hollow teardrop to preview where a linked place's coordinates would
		// drop the pin, before the user accepts.
		const s = 30, h = Math.round(s * 1.15);
		const c = color || '#267b77';
		return L.divIcon({
			className: 'sx-pin-wrapper',
			iconSize: [s, h],
			iconAnchor: [s/2, h],
			html: `<span class="sx-map-pin siraj-pin siraj-pin-ghost" style="--pin-color:${c};width:${s}px;height:${h}px;opacity:.55"><span class="siraj-pin-ring" style="border-color:${c};border-style:dashed"></span><span class="siraj-pin-body" style="width:${Math.round(s*.66)}px;background:transparent;border-color:${c};border-style:dashed"></span><span class="siraj-pin-point" style="border-top-color:${c};opacity:.7"></span></span>`,
		});
	}

	function linkedPlaceCoordinates(state) {
		// Returns {lat, lon, name} if the linked-place field points to a Place
		// doc that is in the form's locals (i.e. fetched with its doc in the
		// same request), null otherwise. Callers must frappe.call a fetch if
		// this returns null; we don't do that automatically to keep the click
		// path honest about network traffic.
		const linkField = state.cfg.linked_place_field;
		if (!linkField) return null;
		const doc = state.frm && state.frm.doc;
		if (!doc) return null;
		const linkDocname = doc[linkField];
		if (!linkDocname) return null;
		// Look in frappe's model cache — populated by add_fetch / link field
		// preload. If we can find a cached Place with lat/lon, use it.
		try {
			const placeDoc = (frappe.get_doc && frappe.get_doc('Place', linkDocname)) || null;
			if (placeDoc && placeDoc.latitude != null && placeDoc.longitude != null) {
				const lat = parseCoordinate(placeDoc.latitude, 90);
				const lon = parseCoordinate(placeDoc.longitude, 180);
				if (lat != null && lon != null) return { lat, lon, name: linkDocname };
			}
		} catch (_) {}
		// Last resort: if the Place is quick-entered inline, it may not be in
		// the model cache. Return just the name so the UI can offer "fetch".
		return { name: linkDocname };
	}

	function syncLinkedChip(state) {
		const head = state.box.find('.siraj-coord-linked-ghost').empty();
		const doc = state.frm && state.frm.doc;
		if (!doc) return;
		const linkField = state.cfg.linked_place_field;
		if (!linkField) return;
		const name = doc[linkField];
		if (!name) return;
		const chip = $('<span class="siraj-coord-chip"></span>')
			.text(name)
			.attr('title', t('Linked place') + ': ' + name)
			.appendTo(head);
		const coord = linkedPlaceCoordinates(state);
		if (coord && coord.lat != null) {
			// Place's coordinates are available — offer the copy action and
			// show a ghost marker on the map preview.
			$('<button type="button" class="siraj-coord-chip-use"></button>')
				.text(t('Use coordinates'))
				.attr('title', t('Copy coordinates from the linked place'))
				.on('click', ev => {
					ev.preventDefault(); ev.stopPropagation();
					applyLinkedCoordinates(state, coord);
				})
				.appendTo(head);
			// Ghost marker only when this doc has no pin yet, so it reads as
			// a suggestion rather than duplicate geometry.
			if (state.ghostMarker) { try { state.map.removeLayer(state.ghostMarker); } catch (_) {} state.ghostMarker = null; }
			const a = parseCoordinate(currentValue(state.lat, doc, state.cfg.lat_field), 90);
			const b = parseCoordinate(currentValue(state.lon, doc, state.cfg.lon_field), 180);
			if (a === null || b === null) {
				const c = (window.sirajColours && window.sirajColours[state.frm.doctype]) || '#267b77';
				state.ghostMarker = L.marker([coord.lat, coord.lon], { icon: ghostIcon(c), interactive: false, keyboard: false }).addTo(state.map);
			}
		} else {
			// Place exists but its coordinates aren't loaded client-side.
			// Provide a "fetch" action that does a silent frappe.call.
			$('<button type="button" class="siraj-coord-chip-fetch"></button>')
				.text(t('Fetch'))
				.attr('title', t('Fetch coordinates of linked place'))
				.on('click', ev => {
					ev.preventDefault(); ev.stopPropagation();
					fetchLinkedPlace(state, name);
				})
				.appendTo(head);
		}
	}

	function fetchLinkedPlace(state, name) {
		if (!name || !state.editable) return;
		frappe.call({
			method: 'frappe.client.get',
			args: { doctype: 'Place', name },
			silent: true,
			callback: res => {
				const d = res && res.message;
				if (!d || d.latitude == null || d.longitude == null) {
					state.status.text(t('Linked place has no coordinates saved.'));
					return;
				}
				applyLinkedCoordinates(state, {
					lat: parseCoordinate(d.latitude, 90),
					lon: parseCoordinate(d.longitude, 180),
					name,
				});
			},
		});
	}

	async function applyLinkedCoordinates(state, coord) {
		if (!state.editable || !coord || coord.lat == null || coord.lon == null) return;
		const values = { [state.cfg.lat_field]: decimalText(coord.lat), [state.cfg.lon_field]: decimalText(coord.lon) };
		if (state.frm.fields_dict.geocoding_method && state.frm.fields_dict.geocoding_method.get_status() === 'Write') {
			values.geocoding_method = 'inherited';
		}
		if (state.frm.fields_dict.geometry_source && state.frm.fields_dict.geometry_source.get_status() === 'Write' && !state.frm.doc.geometry_source) {
			values.geometry_source = 'linked_place';
		}
		try {
			await state.frm.set_value(values);
			update(state.frm, false);
			state.status.text(t('Coordinates copied from linked place.'));
		} catch (_) {
			state.status.text(t('Could not apply coordinates from linked place.'));
		}
	}

	function diagnoseCoordinates(lat, lon, aText, bText) {
		// Return a warning message (or null) describing suspicious input.
		if (lat === null || lon === null) {
			// Determine whether the raw input is a lat-out-of-range that would
			// be a valid longitude (a classic swap) vs just garbage.
			const a = parseCoordinate(String(aText ?? '').trim(), 180);
			const b = parseCoordinate(String(bText ?? '').trim(), 90);
			if (a !== null && Math.abs(a) > 90 && b !== null && Math.abs(b) <= 90) {
				return t('Latitude value is outside −90…90° and looks like a longitude — fields may be swapped.');
			}
			if ((String(aText ?? '').trim() || String(bText ?? '').trim())) {
				return t('Enter valid decimal coordinates: latitude −90 to 90, longitude −180 to 180.');
			}
			return null;
		}
		if (lat === 0 && lon === 0) {
			return t('Zero pair (0,0) shown — this often means "unknown" in legacy data. Confirm before interpreting.');
		}
		return null;
	}

	function update(frm, center = true) {
		// Find any state for this frm (supports multiple coordinate pairs
		// on a single doctype, though we only ship one pair today).
		let anyUpdated = false;
		states.forEach(state => {
			if (state.frm !== frm) return;
			const fields = controlsFor(frm, state.cfg);
			if (!fields || fields.lat !== state.lat || fields.lon !== state.lon) { removeState(state); return; }
			state.editable = fields.editable;
			const a = currentValue(fields.lat, frm.doc, state.cfg.lat_field);
			const b = currentValue(fields.lon, frm.doc, state.cfg.lon_field);
			const lat = parseCoordinate(a, 90), lon = parseCoordinate(b, 180);
			const warning = diagnoseCoordinates(lat, lon, a, b);
			if (lat === null || lon === null) {
				if (state.marker) { state.map.removeLayer(state.marker); state.marker = null; }
				if (state.uncertaintyCircle) { state.map.removeLayer(state.uncertaintyCircle); state.uncertaintyCircle = null; }
				state.status.text(warning || t('Click the map to pick a point, or type coordinates above.'));
				syncLinkedChip(state);
			} else {
				const dt = frm.doctype || 'Place';
				if (!state.marker) {
					state.marker = L.marker([lat, lon], { icon: pinIcon(dt, null, 34), draggable: !!fields.editable, keyboard: true }).addTo(state.map);
					state.marker.on('dragend', () => {
						if (!fields.editable) return;
						const p = state.marker.getLatLng();
						writePoint(frm, state.cfg, p, false);
					});
					state.marker.bindTooltip(__(dt), { direction: 'top', offset: [0, -18] });
				} else {
					state.marker.setLatLng([lat, lon]);
					state.marker.setIcon(pinIcon(dt, null, 34));
				}
				if (state.marker.bringToFront) state.marker.bringToFront();
				drawUncertainty(state, lat, lon);
				syncLinkedChip(state);
				if (center) state.map.setView([lat, lon], Math.max(state.map.getZoom(), 6));
				if (warning) state.status.text(warning);
				else if (!fields.editable) state.status.text(t('Location shown (read-only).'));
				else state.status.text(t('Location shown. Click the map to move the pin, or drag the pin directly.'));
			}
			state.box.toggleClass('siraj-coord-readonly', !fields.editable);
			state.box.toggleClass('siraj-coord-warning', !!warning);
			anyUpdated = true;
		});
		return anyUpdated;
	}

	/* ------- Admin-chain auto-fill (debounced, abortable, diff-aware) ------- */
	let resolveAbort = null;
	function resolveAndApply(frm, cfg, lat, lon) {
		if (resolveAbort) { try { resolveAbort.abort(); } catch(_){} resolveAbort = null; }
		if (!cfg.admin_fields) return;
		if (!frm.fields_dict || !frm.fields_dict.latitude) return;
		const controller = new AbortController();
		resolveAbort = controller;
		setTimeout(async () => {
			if (controller.signal.aborted) return;
			try {
				const r = await frappe.xcall('siraj_research.api.geo_resolve.resolve_point',
					{ latitude: lat, longitude: lon });
				if (controller.signal.aborted) return;
				applyAdminChain(frm, cfg, r);
			} catch (e) {
				// Silent failure — auto-fill is a convenience, never blocks saves.
				try { console.warn('[SIRAJ coord] resolve failed:', e && e.message); } catch(_){}
			}
		}, 350);
	}

	function applyAdminChain(frm, cfg, res) {
		if (!res || res.error) return;
		const updates = {};
		const diffs = [];
		const fields = cfg.admin_fields || {};
		Object.keys(fields).forEach(chainKey => {
			const fieldname = fields[chainKey];
			if (!fieldname || !frm.fields_dict[fieldname]) return;
			const field = frm.fields_dict[fieldname];
			if (field.get_status() !== 'Write') return;
			let value = null;
			if (chainKey === 'place_name') {
				value = res.nearest_place ? (res.nearest_place.name_en || res.nearest_place.name_ar || null) : null;
			} else {
				const node = res.admin_chain && res.admin_chain[chainKey];
				// Link fields want the linked DocType name, but the server
				// returns pcode; if no matching Place exists locally yet we
				// skip (a future Slice-E enhancement will create/link Place
				// records automatically).
				value = node && node.pcode ? node.pcode : (node ? node.name_en : null);
			}
			if (value == null) return;
			const current = (field.$input && field.$input.val()) || (frm.doc && frm.doc[fieldname]) || '';
			if (!current || String(current).trim() === '' || String(current) === value) {
				updates[fieldname] = value;
			} else if (String(current) !== String(value)) {
				diffs.push({ fieldname, label: field.df.label || fieldname, current, proposed: value });
			}
		});
		if (diffs.length === 0 && Object.keys(updates).length) {
			// No conflicts — write silently.
			Object.keys(updates).forEach(k => { try { frm.set_value(k, updates[k]); } catch(_){} });
		} else if (diffs.length) {
			// Show a Keep/Replace/Replace-all diff dialog. Never overwrite
			// without user confirmation (existing values may come from human
			// research).
			showDiffDialog(frm, cfg, updates, diffs, res);
		}
	}

	function showDiffDialog(frm, cfg, updates, diffs, res) {
		const d = new frappe.ui.Dialog({
			title: t('Administrative auto-fill'),
			fields: [
				{ fieldtype:'HTML', fieldname:'summary', label:'summary' },
			],
			primary_action_label: t('Replace with detected'),
			secondary_action_label: t('Keep existing'),
			primary_action() {
				const merge = Object.assign({}, updates);
				diffs.forEach(x => { merge[x.fieldname] = x.proposed; });
				Object.keys(merge).forEach(k => { try { frm.set_value(k, merge[k]); } catch(_){} });
				d.hide();
			},
		});
		let html = '<div style="font-size:13px;line-height:1.5">';
		html += '<p>' + t('The following fields already have values that differ from what the boundary dataset detected at this point:') + '</p><ul>';
		diffs.forEach(x => { html += '<li><b>' + frappe.utils.escape_html(x.label) + '</b>: ' + frappe.utils.escape_html(String(x.current)) + ' → <code>' + frappe.utils.escape_html(String(x.proposed)) + '</code></li>'; });
		html += '</ul><p style="color:var(--text-muted);font-size:12px">' + t('"Replace" overwrites; "Keep existing" leaves your values. New/empty fields (' + Object.keys(updates).length + ') will be filled either way.') + '</p>';
		if (res.ambiguous) html += '<p style="color:#8a2525">⚠ ' + t('This point is near a boundary; values may be inaccurate.') + '</p>';
		if (res.nearest_place) html += '<p>' + t('Nearest settlement') + ': <b>' + frappe.utils.escape_html(res.nearest_place.name_en || '') + '</b> — ' + Math.round(res.nearest_place.distance_m) + ' m</p>';
		html += '</div>';
		d.fields_dict.summary.$wrapper.html(html);
		d.show();
	}

	async function writePoint(frm, cfg, latlng, doMove = true) {
		const state = [...states.values()].find(s => s.frm === frm && s.cfg === cfg);
		if (!state || !state.editable) return;
		const latitude = Number(latlng.lat), longitude = Number(latlng.lng);
		if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return;
		const values = { [cfg.lat_field]: decimalText(latitude), [cfg.lon_field]: decimalText(longitude) };
		if (frm.fields_dict.geocoding_method && frm.fields_dict.geocoding_method.get_status() === 'Write') {
			values.geocoding_method = 'map_pick';
		}
		if (frm.fields_dict.geometry_source && frm.fields_dict.geometry_source.get_status() === 'Write' && !frm.doc.geometry_source) {
			values.geometry_source = 'map_pick';
		}
		try {
			await frm.set_value(values);
			if (doMove && state.marker) state.marker.setLatLng([latitude, longitude]);
			update(frm, false);
			// Fire admin-chain auto-fill (debounced + diff-aware).
			resolveAndApply(frm, cfg, latitude, longitude);
		} catch (_) {
			state.status.text(t('Could not update the coordinate fields.'));
		}
	}

	async function mount(frm, cfg) {
		const key = stateKey(frm, cfg);
		const old = states.get(key);
		const fields = controlsFor(frm, cfg);
		// If lat/lon disappeared (Customize Form removed them), permissions
		// were revoked to None, or the wrapper detached, tear down any map
		// we previously mounted for this pair.
		if (!fields || !fields.lon.$wrapper || !fields.lon.$wrapper.length || !fields.lon.$wrapper.length) {
			if (old) removeState(old);
			return;
		}
		if (old && old.docname === frm.docname && old.lat === fields.lat && old.lon === fields.lon && old.box[0].isConnected) {
			update(frm);
			setTimeout(() => { if (states.get(key) === old) old.map.invalidateSize(); }, 0);
			return;
		}
		if (old) removeState(old);

		const docname = frm.docname || ('new-' + (++instanceCounter));
		try { await assets(); } catch (_) { return; }

		const current = controlsFor(frm, cfg);
		if (frm.docname !== docname.replace(/^new-\d+$/, () => frm.docname) && !String(docname).startsWith('new-')) return;
		if (!current || current.lat !== fields.lat || current.lon !== fields.lon) return;
		if (states.has(key)) return;

		// Mount as a real Frappe .form-group row inside the section so the
		// map participates in column/flex layout, RTL, and print styles.
		const $sectionBody = fields.lon.$wrapper.closest('.form-section').find('.section-body').first();
		const $anchor = fields.lon.$wrapper.closest('.frappe-control').addBack().last();
		const box = $('<div class="siraj-coordinate-map"></div>')
			.attr('data-siraj-build', window.SIRAJ_BUILD || '')
			.attr('data-doctype', frm.doctype)
			.attr('data-fieldname', '__coordinate_map_' + cfg.lat_field);
		const group = $('<div class="frappe-control siraj-coord-group form-group"></div>')
			.attr('data-fieldname', '__coordinate_map_' + cfg.lat_field)
			.attr('data-siraj-build', window.SIRAJ_BUILD || '')
			.append(box);
		const heading = $('<div class="siraj-coord-head"></div>').appendTo(box);
		$('<strong></strong>').text(t('Coordinate map')).appendTo(heading);
		$('<span class="siraj-coord-linked-ghost"></span>').appendTo(heading);
		const help = $('<div class="siraj-coord-help"></div>')
			.text(t('Click the map to place the pin, or drag the pin to move it. Tools live in the dock on the right edge of the map.'))
			.appendTo(box);
		const canvas = $('<div role="region" class="siraj-coord-canvas"></div>')
			.attr('aria-label', t('Coordinate map'))
			.appendTo(box);
		const status = $('<div role="status" aria-live="polite" class="siraj-coord-status"></div>').appendTo(box);
		if ($anchor.length) $anchor.after(group);
		else if ($sectionBody.length) $sectionBody.append(group);
		else fields.lon.$wrapper.after(box);

		// autoPanPadding keeps edge pins/popups inside the visible canvas rather
		// than spilling outside the frame (we removed overflow:visible from the
		// container so panes cannot bleed into form sidebars; pan-inside is how
		// we still keep pins legible at the edge).
		const map = L.map(canvas[0], {
			maxZoom: 22, scrollWheelZoom: false, zoomControl: false,
			zoomSnap: 0.25,
			autoPanPadding: [60, 60],
			autoPanPaddingTopLeft: null,
			autoPanPaddingBottomRight: null,
		}).setView([33.3152, 44.3661], 4);
		L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
		if (map.attributionControl) map.attributionControl.addAttribution('Natural Earth');

		const state = {
			key, cfg, lat: fields.lat, lon: fields.lon, docname, box, group, map, status,
			marker: null, tileLayer: null, offlineLayer: null, packLayer: null, editable: current.editable,
			uncertaintyCircle: null, ghostMarker: null, frm,
			tabObserver: null, sectionObserver: null, resizeObserver: null,
		};
		states.set(key, state);

		// Resize when the canvas changes size, the tab shows, or the
		// enclosing section collapses/expands. We observe attribute and
		// class changes on ancestors so both Frappe's .tab-pane active
		// toggle and .section.collapsed are caught.
		if (window.ResizeObserver) {
			state.resizeObserver = new ResizeObserver(() => {
				if (states.get(key) !== state) return;
				const w = canvas[0].clientWidth, h = canvas[0].clientHeight;
				if (!w || !h) return;  // zero-size container → NaN LatLng from unproject
				// Guard: only invalidate when size differs from Leaflet's cached size.
				const sz = map.getSize && map.getSize();
				if (sz && Math.abs(sz.x - w) < 1 && Math.abs(sz.y - h) < 1) return;
				map.invalidateSize();
			});
			state.resizeObserver.observe(canvas[0]);
		}
		state.tabObserver = new MutationObserver(() => {
			if (!canvas[0].isConnected) return;
			const w = canvas[0].clientWidth, h = canvas[0].clientHeight;
			const hidden = !canvas[0].offsetParent || !w || !h;
			if (!hidden) setTimeout(() => { if (canvas[0].clientWidth && canvas[0].clientHeight) map.invalidateSize(); }, 30);
		});
		state.tabObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class','style','hidden','aria-hidden'] });

		// Click-to-pick via shared MeasureTool.
		const Kit = window.SirajMapKit;
		state.measure = new Kit.MeasureTool(map, {
			onStatus: text => status.text(text),
			onPick: latlng => { if (current.editable) writePoint(frm, cfg, latlng); },
		});

		// Default click places the pin when no tool is active.
		map.on('click', e => {
			if (state.measure.isActive && state.measure.isActive()) return;
			if (current.editable) writePoint(frm, cfg, e.latlng);
		});

		/* ------ Toolbar (shared declarative registry, form-map subset) ------ */
		const toolbar = L.control.sirajToolbar({ position: 'topright' }).addTo(map);
		state.toolbar = toolbar;
		const localPacks = new Map();

		toolbar.group(t('Navigate'))
			.add({ icon: 'zoom_in',  label: t('In'),   action: () => map.zoomIn() })
			.add({ icon: 'zoom_out', label: t('Out'),  action: () => map.zoomOut() })
			.add({ icon: 'home',     label: t('Home'), action: () => map.setView([33.3152, 44.3661], 4) })
			.add({ icon: 'locate_me', label: t('My loc'), action: () => map.locate({ setView: true, maxZoom: 12, enableHighAccuracy: true }) });

		const selectBasemap = val => {
			if (state.tileLayer) { map.removeLayer(state.tileLayer); state.tileLayer = null; }
			if (state.packLayer) { map.removeLayer(state.packLayer); state.packLayer = null; }
			map.setMinZoom(0);
			const pack = localPacks.get(String(val).replace(/^pack-/, ''));
			if (pack) {
				if (state.offlineLayer) map.removeLayer(state.offlineLayer);
				map.setMinZoom(pack.minzoom);
				state.packLayer = L.tileLayer('/api/method/siraj_research.local_maps.tile?kind=' + encodeURIComponent(pack.kind) + '&z={z}&x={x}&y={y}', {
					minZoom: pack.minzoom, maxZoom: 22, maxNativeZoom: pack.maxzoom, attribution: pack.attribution || '',
				}).addTo(map);
				state.packLayer.on('tileerror', () => status.text(t('Some local tiles are unavailable at this location or zoom.')));
			} else if (val === 'online') {
				if (state.offlineLayer) map.removeLayer(state.offlineLayer);
				state.tileLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
					maxZoom: 22, maxNativeZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
				}).addTo(map);
				status.text(t('Online tiles disclose your IP address and viewed area to OpenStreetMap.'));
			} else {
				if (state.offlineLayer) state.offlineLayer.addTo(map).bringToBack();
			}
		};
		const basemapMenu = pop => {
			const w = $('<div></div>').appendTo(pop);
			const opt = (val, icon, label, active) => {
				const b = $('<button type="button" class="siraj-toolbar-opt"></button>')
					.html((window.sirajIcons ? window.sirajIcons.toolSvg(icon, { size: 16 }) : '') + '<span>' + label + '</span>');
				if (active) b.addClass('is-active');
				b.on('click', () => { w.find('.is-active').removeClass('is-active'); b.addClass('is-active'); selectBasemap(val); });
				b.appendTo(w); return b;
			};
			opt('local', 'offline', t('Offline basemap'), true);
			opt('online', 'online', t('Online: OpenStreetMap'), false);
			$('<hr>').appendTo(w);
			$('<div style="font-size:11px;color:var(--text-muted);padding:4px"></div>').text(t('Downloaded local packs appear here.')).appendTo(w);
			frappe.call({ method: 'siraj_research.local_maps.available_packs', type: 'GET', silent: true }).then(res => {
				if (states.get(key) !== state || !Array.isArray(res.message)) return;
				res.message.forEach(pack => {
					if (pack.unavailable || !['standard', 'aerial'].includes(pack.kind)) return;
					localPacks.set(pack.kind, pack);
					opt('pack-' + pack.kind, 'layers', pack.kind === 'aerial' ? t('Local aerial') : t('Local standard'), false);
				});
			}).catch(() => {});
		};
		toolbar.group(t('Basemap'))
			.add({ icon: 'layers', label: t('Basemap'), menuTitle: t('Basemap'), menu: basemapMenu });

		toolbar.separator();

		toolbar.group(t('Measure'))
			.add({ icon: 'ruler',  label: t('Distance'), action: () => state.measure.activate('distance') })
			.add({ icon: 'area',   label: t('Area'),     action: () => state.measure.activate('area') })
			.add({ icon: 'radius', label: t('Radius'),   action: () => state.measure.activate('radius') })
			.add({ icon: 'bearing',label: t('Bearing'),  action: () => state.measure.activate('bearing') })
			.add({ icon: 'clear',  label: t('Clear'),    action: () => state.measure.clear() });

		toolbar.separator();

		toolbar.group(t('Point'))
			.add({ icon: 'pick',  label: t('Pick'), action: () => {
				if (!current.editable) { status.text(t('You do not have write access to these coordinates.')); return; }
				status.text(t('Click the map to place this record.'));
				state.measure.activate('pick');
			}})
			.add({ icon: 'clear', label: t('Clear'), action: async () => {
				if (!current.editable || frm.docname !== state.docname) return;
				const values = { [cfg.lat_field]: '', [cfg.lon_field]: '' };
				try { await frm.set_value(values); update(frm, false); }
				catch (_) { status.text(t('Could not clear the coordinate fields.')); }
			}});

		// Wire input fields for bidirectional sync.
		for (const field of [fields.lat, fields.lon]) {
			field.$input?.off('.sirajCoordinates').on('input.sirajCoordinates change.sirajCoordinates', () => update(frm, false));
		}

		update(frm, true);
		// Defer initial invalidateSize until the canvas has a real size.
		// Force-call invalidateSize the moment the canvas is non-trivial
		// (earlier code returned early if size matched cached size, but on
		// first paint Leaflet initialized at 0×0 and never refreshed even
		// when the wrapper later had height).
		const tryInv = delay => setTimeout(() => {
			if (states.get(key) !== state) return;
			const w = canvas[0].clientWidth, h = canvas[0].clientHeight;
			if (w > 100 && h > 100) {
				map.invalidateSize(false);  // animate=false; force re-layout
				return;
			}
			if (delay < 1600) tryInv(delay * 2);
		}, delay);
		tryInv(30);
		// Belt-and-suspenders: also invalidate on the next two animation
		// frames and after a longer timeout to catch slow Frappe layouts.
		requestAnimationFrame(() => { if (states.get(key) === state) map.invalidateSize(false); });
		setTimeout(() => { if (states.get(key) === state) map.invalidateSize(false); }, 500);

		// Load offline base layer (Natural Earth countries-110m topojson).
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (!response.ok) throw new Error('basemap');
			const world = await response.json();
			if (states.get(key) !== state) return;
			state.offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
				style: { color: '#7793a0', weight: 1, fillColor: '#eef3ed', fillOpacity: 1, interactive: false },
			});
			if (!state.tileLayer && !state.packLayer) state.offlineLayer.addTo(map);
			if (state.marker && state.marker.bringToFront) state.marker.bringToFront();
		} catch (_) {
			if (states.get(key) === state) status.text(t('Offline basemap could not be loaded. Online tiles remain optional.'));
		}

		// Advanced overlays (coordinate readout + stats dock + minimap).
		if (window.SirajMapAdvanced) {
			const adv = window.SirajMapAdvanced.attach(map, {
				getData: () => {
					const c = frm.doc;
					const hasCoord = c && isFinite(Number(c[cfg.lat_field])) && isFinite(Number(c[cfg.lon_field]));
					return {
						total: 1, visible: hasCoord ? 1 : 0,
						selected: 0, edges: 0,
						typeCounts: { [frm.doctype]: hasCoord ? 1 : 0 },
					};
				},
				readout: {
					onClick: () => {
						const lat = frm.doc[cfg.lat_field], lon = frm.doc[cfg.lon_field];
						if (isFinite(Number(lat)) && isFinite(Number(lon)) && navigator.clipboard) {
							navigator.clipboard.writeText(Number(lat).toFixed(6)+', '+Number(lon).toFixed(6))
								.then(()=>status.text(t('Coordinates copied to clipboard.')))
								.catch(()=>{});
						}
					},
				},
			});
			$(fields.lat.$input).add(fields.lon.$input).on('change.sirajCoordinates', () => adv.refresh());
		}
	}

	function mountAllFor(frm) {
		if (!frm || !frm.doctype) return;
		// Register once per doctype so native field change events (when user
		// types into latitude/longitude) trigger update.
		if (!registered.has(frm.doctype)) {
			registered.add(frm.doctype);
			frappe.ui.form.on(frm.doctype, {
				refresh(frm2) { setTimeout(() => mountAllFor(frm2), 0); },
			});
			// Dynamic per-field handlers are lightweight: just call update.
			const cfg = docConfig(frm.doctype);
			[cfg.lat_field, cfg.lon_field].forEach(fn => {
				frappe.ui.form.on(frm.doctype, {
					[fn](frm2) { update(frm2); },
				});
			});
		}
		// Mount an editor for every cfg whose lat/lon fields exist on the form.
		const cfgs = [];
		if (frm.fields_dict && frm.fields_dict[docConfig(frm.doctype).lat_field]
			&& frm.fields_dict[docConfig(frm.doctype).lon_field]) {
			cfgs.push(docConfig(frm.doctype));
		}
		// Also mount for any lat/lon pair that isn't the declared one (future
		// multi-coordinate forms). Keyed on the pair so they don't collide.
		if (frm.fields_dict) {
			const fieldNames = Object.keys(frm.fields_dict);
			for (const fn of fieldNames) {
				const m = fn.match(/^(.+)_latitude$/);
				if (m && fieldNames.includes(m[1] + '_longitude')) {
					cfgs.push({
						lat_field: fn, lon_field: m[1] + '_longitude',
						uncertainty_field: (m[1] + '_geo_uncertainty_m'),
						linked_place_field: null, silhouette: 'pin',
					});
				}
			}
		}
		if (!cfgs.length) {
			// Tear down any orphaned state for this frm (e.g. DocType whose
			// fields changed after a Customize Form).
			states.forEach(s => { if (s.frm === frm) removeState(s); });
			return;
		}
		cfgs.forEach(c => mount(frm, c));
	}

	$(document).on('form-refresh.sirajCoordinates', (_e, frm) => {
		setTimeout(() => mountAllFor(frm), 0);
	});

	// Expose module version + config for Diagnostics.
	window.SIRAJ_COORDINATE_MAP_VERSION = MODULE_VERSION;
	window.SIRAJ_COORDINATE_DOCS_ACTIVE = DEFAULT_COORDS;
})();
