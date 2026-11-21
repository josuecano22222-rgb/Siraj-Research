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
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', village:'village', community:'community', place_name:'place_name' } },
		'Institution':            { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'place',         silhouette:'building',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', village:'village', community:'community', place_name:'place_name' } },
		'Place':                  { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'parent_place',  silhouette:'pin',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', village:'village', community:'community' } },
		'Siraj Event':         { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'place',         silhouette:'star',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', village:'village', community:'community', place_name:'place_name' } },
		'Military Unit':          { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'linked_place',  silhouette:'shield',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', village:'village', community:'community' } },
		'Operational Deployment': { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:null,            silhouette:'crosshair',
			admin_fields: { country:'country', governorate:'governorate', district:'district', municipality:'municipality', village:'village', place_name:'location' } },
	};
	function docConfig(doctype) {
		const fromBoot = (window.sirajCoordinateDocs && window.sirajCoordinateDocs[doctype]) || {};
		return Object.assign({
			lat_field: 'latitude', lon_field: 'longitude',
			map_field: 'geo_point', origin_confirmed_field: 'coordinate_origin_confirmed',
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
				// Install eagerly if the bundle evaluated before Leaflet (the
				// lazy frappe.require above just loaded it). The toolbar's own
				// polling is only a fallback.
				if (window.L && window.SirajMapToolbar && window.SirajMapToolbar.install) {
					try { window.SirajMapToolbar.install(window.L); } catch (_) {}
				}
				// siraj-map-toolbar.js installs itself after Leaflet appears;
				// wait for both SirajMapKit and the toolbar control so mount()
				// never sees L.control.sirajToolbar === undefined.
				return new Promise(res => {
					const started = Date.now();
					const check = () => {
						if (window.SirajMapKit && window.L) {
							if (window.L.control && window.L.control.sirajToolbar) return res();
							// The toolbar is an enhancement. Never block the whole
							// form map forever if its optional registration fails.
							if (Date.now() - started > 3000) {
								try { console.warn('[SIRAJ coord] toolbar unavailable; mounting map without it'); } catch (_) {}
								return res();
							}
						}
						setTimeout(check, 30);
					};
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
		// No scientific notation in text input — keep the string semantics
		// identical to SirajGeoPointCore's DECIMAL (test_siraj_geopoint_core).
		// Number values still pass through above; picker writes go through
		// decimalText(), so exponent text only appears for <1e-6 deg edges.
		if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized)) return null;
		const n = Number(normalized);
		if (!Number.isFinite(n) || decimalExceeds(normalized, max)) return null;
		return n;
	}
	// Exact decimal bound test on the raw text: Number() rounds
	// "90.000…001" (51 fraction digits) to exactly 90 and would wrongly
	// accept an input that is definitively past the bound.
	function decimalExceeds(text, max) {
		const negative = text.startsWith('-');
		const body = negative ? text.slice(1) : text;
		const dot = body.indexOf('.');
		const whole = (dot === -1 ? body : body.slice(0, dot)) || '0';
		const frac = dot === -1 ? '' : body.slice(dot + 1);
		const scale = 10n ** BigInt(frac.length);
		const value = BigInt(whole + frac) * (negative ? -1n : 1n);
		const bound = BigInt(max) * scale;
		return value > bound || value < -bound;
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

	function originConfirmed(frm, cfg) {
		const field = cfg.origin_confirmed_field;
		return !!(field && frm && frm.doc && (frm.doc[field] === 1 || frm.doc[field] === '1' || frm.doc[field] === true));
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
			// (0,0) is ambiguous in legacy Float data: a filled pair often
			// meant "unset", but it can also be a real origin. Do not draw a
			// misleading pin until the researcher explicitly confirms it.
			const zeroPair = lat === 0 && lon === 0 && !originConfirmed(frm, state.cfg);
			if (lat === null || lon === null || zeroPair) {
				if (state.marker) { state.map.removeLayer(state.marker); state.marker = null; }
				if (state.uncertaintyCircle) { state.map.removeLayer(state.uncertaintyCircle); state.uncertaintyCircle = null; }
				if (zeroPair) {
					state.status.empty().append(
						$('<span></span>').text(t('Coordinates are exactly (0,0). This is treated as unset until confirmed.'))
					);
					if (fields.editable) {
						$('<button type="button" class="siraj-coord-confirm-zero"></button>')
							.text(t('Confirm 0,0 as a real point'))
							.on('click', async ev => {
								ev.preventDefault(); ev.stopPropagation();
								try {
									await frm.set_value(state.cfg.origin_confirmed_field, 1);
									update(frm, false);
								} catch (_) { state.status.text(t('Could not confirm the origin point.')); }
							})
							.appendTo(state.status);
					}
				} else {
					state.status.text(warning || t('Click the map to pick a point, or type coordinates above.'));
				}
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
		if (!frm.fields_dict || !frm.fields_dict[cfg.lat_field]) return;
		// An unconfirmed zero pair is legacy "unset" data, not a location.
		if (lat === 0 && lon === 0 && !originConfirmed(frm, cfg)) return;
		const controller = new AbortController();
		resolveAbort = controller;
		setTimeout(async () => {
			if (controller.signal.aborted) return;
			try {
				let r = null;
				// Authoritative path first: hierarchy_for_point creates/reuses
				// the linked hierarchy rows and returns their real DocType names.
				// Writing raw P-Codes into Link fields causes a save-time
				// LinkValidationError, so never auto-fill from the loose
				// resolver payload unless no linked result is available.
				if (window.SirajHierarchy && window.SirajHierarchy.resolve) {
					try {
						r = await window.SirajHierarchy.resolve(lat, lon, {
							createMissing: true, useOnline: true,
						});
					} catch (_) { r = null; }
				}
				if (!r || r.error) {
					if (window.SirajHierarchy && window.SirajHierarchy.resolve) {
						// Force the worker path but still use the shared
						// normaliser, so offline rows carry real linked names.
						try { r = await window.SirajHierarchy.resolve(lat, lon, { offlineOnly: true }); }
						catch (_) { r = null; }
					}
				}
				if ((!r || r.error) && !(window.SirajHierarchy && window.SirajHierarchy.resolve)) {
					// Legacy fallback when the shared hierarchy module is not
					// loaded: Data fields only, never Link fields.
					if (window.SirajGeo && window.SirajGeo.resolve) {
						try { r = await window.SirajGeo.resolve(lat, lon); } catch(_) { r = null; }
					}
					if (!r || !r.on_land) {
						try {
							r = await frappe.xcall('siraj_research.api.geo_resolve.resolve_point',
								{ latitude: lat, longitude: lon, use_online: 1 });
						} catch (_) { /* keep worker result or null */ }
					}
				}
				if (controller.signal.aborted) return;
				applyAdminChain(frm, cfg, r);
				if (window.SirajHierarchy && window.SirajHierarchy.refreshForm) {
					window.SirajHierarchy.refreshForm(frm, cfg, lat, lon).then(h => {
						if (!h || controller.signal.aborted) return;
						const state = [...states.values()].find(st => st.frm === frm && st.cfg === cfg);
						if (!state) return;
						const deepest = h.deepest_level >= 0
							? ((h.levels[h.deepest_level] || {}).label_en || '') : '';
						const missing = (h.gaps || []).length;
						if (deepest) state.status.text(
							t('Resolved to {0}.', [deepest]) +
							(missing ? ' ' + t('{0} levels not covered by the dataset.', [missing]) : '')
						);
					}).catch(() => {});
				}
			} catch (e) {
				try { console.warn('[SIRAJ coord] resolve failed:', e && e.message); } catch(_){}
			}
		}, 350);
	}

	// Manually typed coordinates must resolve too, not only map picks. A
	// debounce keeps rapid typing cheap; parseCoordinate accepts eastern digits.
	let manualResolveTimer = null;
	function resolveFromInputs(frm, cfg) {
		if (manualResolveTimer) clearTimeout(manualResolveTimer);
		manualResolveTimer = setTimeout(() => {
			const doc = frm.doc || {};
			const lat = parseCoordinate(currentValue(frm.fields_dict[cfg.lat_field], doc, cfg.lat_field), 90);
			const lon = parseCoordinate(currentValue(frm.fields_dict[cfg.lon_field], doc, cfg.lon_field), 180);
			if (lat != null && lon != null) {
				if (!(lat === 0 && lon === 0 && !originConfirmed(frm, cfg))) {
					resolveAndApply(frm, cfg, lat, lon);
				}
				syncMapField(frm, cfg, lat, lon);
			}
		}, 600);
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
				value = res.nearest_place_name
					|| (res.nearest_place ? (res.nearest_place.name_en || res.nearest_place.name_ar || null) : null);
			} else {
				const isLink = field.df && field.df.fieldtype === 'Link';
				const row = res.by_field && res.by_field[chainKey];
				if (row) {
					// hierarchy_for_point returns a *linked* DocType name. Only
					// that is safe to write into a Link field; a P-Code or label
					// would be accepted by the client but rejected on save.
					if (isLink) {
						value = (row.status === 'linked' && row.name) ? row.name : null;
					} else {
						value = row.name || row.code || row.label_en || null;
					}
				} else {
					// Legacy/offline resolver payload. Never write its P-Code
					// into a Link field; Data fields can still show the label.
					const node = res.admin_chain && res.admin_chain[chainKey];
					value = isLink ? null : (node ? (node.name_en || node.pcode || null) : null);
				}
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

	function syncMapField(frm, cfg, lat, lon) {
		const helpers = window.SirajGeoPointCore;
		const name = cfg.map_field;
		if (!helpers || !name || !frm.fields_dict || !frm.fields_dict[name]) return;
		const control = frm.fields_dict[name];
		if (!control.df || control.df.fieldtype !== 'Geolocation') return;
		if (typeof control.get_status === 'function' && control.get_status() !== 'Write') return;
		const zero = helpers.isZero(lat, lon);
		const originField = cfg.origin_confirmed_field;
		const confirmed = originField && frm.doc && [1, '1', true].includes(frm.doc[originField]);
		const value = (zero && !confirmed) ? '' : helpers.encode(lat, lon, { source: 'siraj_coordinate_map' });
		if (!value || String(frm.doc[name] || '') === value) return;
		try { frm.set_value(name, value); } catch (_) {}
	}

	async function writePoint(frm, cfg, latlng, doMove = true) {
		const state = [...states.values()].find(s => s.frm === frm && s.cfg === cfg);
		if (!state || !state.editable) return;
		const latitude = Number(latlng.lat), longitude = Number(latlng.lng);
		if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return;
		const values = { [cfg.lat_field]: decimalText(latitude), [cfg.lon_field]: decimalText(longitude) };
		syncMapField(frm, cfg, latitude, longitude);
		if (latitude === 0 && longitude === 0 && cfg.origin_confirmed_field
			&& frm.fields_dict[cfg.origin_confirmed_field]
			&& frm.fields_dict[cfg.origin_confirmed_field].get_status() === 'Write') {
			// Choosing the point on the map is an explicit confirmation that
			// the origin is real, unlike a legacy Float default.
			values[cfg.origin_confirmed_field] = 1;
		}
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
		// When the DocType has a native Geolocation field, mount the enhanced
		// map INSIDE that field: the field remains the visible, real field
		// while the stock Leaflet canvas is replaced by our cached, switchable
		// map with hierarchy support.
		const $sectionBody = fields.lon.$wrapper.closest('.form-section').find('.section-body').first();
		const $anchor = fields.lon.$wrapper.closest('.frappe-control').addBack().last();
		const mapControl = cfg.map_field && frm.fields_dict && frm.fields_dict[cfg.map_field];
		const $nativeWrapper = (mapControl && mapControl.df && mapControl.df.fieldtype === 'Geolocation')
			? (mapControl.$wrapper || null) : null;
		if ($nativeWrapper) {
			$nativeWrapper.find('.map-wrapper').hide();
			// Stop the stock map from requesting uncached tiles. Frappe may
			// recreate it on refresh; mount() runs again and hides it anew.
			if (mapControl.map) {
				try { mapControl.map.remove(); } catch (_) {}
				mapControl.map = null;
			}
			// Some Frappe forms (notably new docs opened from quick entry)
			// do not initialize `frm.flags` until later in the lifecycle.
			frm.flags = frm.flags || {};
			frm.flags.siraj_custom_map = true;
		}
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
		// Anchor after longitude (inside the Location section). The native
		// Geolocation wrapper can be hidden by Frappe's read-only/permission
		// layout; anchoring to longitude keeps the enhanced map visible even
		// when the stock control itself is not.
		if ($anchor.length) $anchor.after(group);
		else if ($nativeWrapper && $nativeWrapper.length) $nativeWrapper.append(group);
		else if ($sectionBody.length) $sectionBody.append(group);
		else fields.lon.$wrapper.after(box);

		// Defer L.map until canvas is sized (see Explorer geography() for
		// explanation). Frappe form sections can collapse/expand; mapping at
		// 0x0 projects tiles to pixel (0,0) and they never paint, and mousemove
		// events against the zero-size CRS throw Invalid LatLng NaN.
		//
		// We also apply a .is-zero-size class while hidden so CSS blocks pointer
		// events before Leaflet ever receives them — this is the last-resort
		// guard for the Institution tab (where the Position section starts
		// hidden and Leaflet gets mouse events during tab-switch layout).
		const boxEl = box[0];
		function refreshSizeClass() {
			const w = canvas[0].clientWidth, h = canvas[0].clientHeight;
			boxEl.classList.toggle('is-zero-size', !(w > 20 && h > 20));
			return w > 20 && h > 20;
		}
		refreshSizeClass();
		await new Promise(resolve => {
			const tryInit = delay => {
				if (!document.body.contains(canvas[0])) return resolve('gone');
				if (refreshSizeClass()) return resolve('ready');
				if (delay > 1500) return resolve('timeout');
				setTimeout(() => tryInit(delay * 2), delay);
			};
			tryInit(10);
			requestAnimationFrame(() => tryInit(20));
		});

		// If canvas is still 0×0 after the deferral, do NOT call L.map() yet.
		// Re-attempt once a ResizeObserver/MutationObserver/tab event makes it
		// non-trivial.
		let map = null;
		const initCenter = [33.3152, 44.3661], initZoom = 4;
		function constructMap() {
			if (map) return true;
			if (!refreshSizeClass()) return false;
			map = L.map(canvas[0], {
				maxZoom: 22, scrollWheelZoom: false, zoomControl: false,
				zoomSnap: 0.25,
				autoPanPadding: [60, 60],
				autoPanPaddingTopLeft: null,
				autoPanPaddingBottomRight: null,
			});
			map.setView(initCenter, initZoom);
			L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
			if (map.attributionControl) map.attributionControl.addAttribution('Natural Earth');
			return true;
		}
		if (!constructMap()) {
			// Canvas is still hidden — watch for size changes via a temporary
			// ResizeObserver, then fall through to wire up the rest once the
			// map actually exists.
			let ro, to;
			await new Promise(resolve => {
				const tryAgain = () => { if (constructMap()) { cleanup(); resolve(); } };
				ro = new ResizeObserver(tryAgain);
				ro.observe(canvas[0]);
				const mo = new MutationObserver(tryAgain);
				mo.observe(document.body, { childList:true, subtree:true, attributes:true, attributeFilter:['class','style','hidden','aria-hidden'] });
				$(document).on('shown.bs.tab', tryAgain);
				to = setTimeout(() => { cleanup(); resolve(); }, 8000);
				function cleanup() {
					try { ro.disconnect(); } catch(_){}
					try { mo.disconnect(); } catch(_){}
					try { $(document).off('shown.bs.tab', tryAgain); } catch(_){}
					try { clearTimeout(to); } catch(_){}
				}
			});
		}
		if (!map) {
			// Even after waiting the canvas is hidden — give up. Mount will retry
			// next refresh.
			group.remove();
			return;
		}

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
		const safeInvalidate = () => {
			if (states.get(key) !== state) return;
			if (!refreshSizeClass()) return;
			try { map.invalidateSize(false); } catch (_) {}
		};
		// Invalidate size on tab switch (Bootstrap fires shown.bs.tab on the
		// newly-activated tab-link) and on MutationObserver class changes.
		const onTabShow = () => setTimeout(safeInvalidate, 60);
		$(document).on('shown.bs.tab', 'a[data-toggle="tab"]', onTabShow);
		state._offTab = () => $(document).off('shown.bs.tab', 'a[data-toggle="tab"]', onTabShow);
		state.tabObserver = new MutationObserver(() => {
			if (!canvas[0].isConnected) return;
			const w = canvas[0].clientWidth, h = canvas[0].clientHeight;
			const hidden = !canvas[0].offsetParent || !w || !h;
			if (!hidden) setTimeout(safeInvalidate, 30);
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
		// The map must remain usable even when the optional toolbar is not
		// registered. A chainable no-op keeps every toolbar pack below safe.
		const fallbackToolbar = () => {
			const api = {
				_buttons: new Map(),
				addTo: () => api, group: () => api, add: () => api,
				separator: () => api, remove: () => api,
			};
			return api;
		};
		const toolbar = (L.control && L.control.sirajToolbar)
			? L.control.sirajToolbar({ position: 'topright' }).addTo(map)
			: fallbackToolbar();
		state.toolbar = toolbar;
		const localPacks = new Map();

		toolbar.group(t('Navigate'))
			.add({ icon: 'zoom_in',  label: t('In'),   action: () => map.zoomIn() })
			.add({ icon: 'zoom_out', label: t('Out'),  action: () => map.zoomOut() })
			.add({ icon: 'home',     label: t('Home'), action: () => map.setView([33.3152, 44.3661], 4) })
			.add({ icon: 'locate_me', label: t('My loc'), action: () => map.locate({ setView: true, maxZoom: 12, enableHighAccuracy: true }) });

		// The hierarchy tool is an enhancement: a toolbar/API problem here
		// must never abort the rest of the map setup and leave a blank canvas.
		try {
			toolbar.group(t('Geography'))
				.add({ icon: 'link_chain', label: t('Resolve hierarchy'), tooltip: t('Resolve the full hierarchy at the pin'),
					action: () => {
						const doc = frm.doc || {};
						const lat = parseCoordinate(currentValue(fields.lat, doc, cfg.lat_field), 90);
						const lon = parseCoordinate(currentValue(fields.lon, doc, cfg.lon_field), 180);
						if (lat == null || lon == null) {
							state.status.text(t('Enter or pick valid coordinates first.'));
							return;
						}
						resolveAndApply(frm, cfg, lat, lon);
						try {
							if (window.SirajHierarchy) window.SirajHierarchy.refreshForm(frm, cfg, lat, lon, { force: true });
						} catch (hierr) {
							console.warn('[SIRAJ coord] hierarchy refresh failed:', hierr && hierr.message);
						}
					} });
		} catch (err) {
			console.warn('[SIRAJ coord] hierarchy tool unavailable:', err && err.message);
		}

		// Basemap switcher (Standard / Satellite / Hybrid / Offline) — shared
		// Leaflet controller that adds a toolbar group and persists the choice.
		const basemap = window.SirajBasemap.attach(map, { offlineLayer: null });
		basemap.toolbarGroup(toolbar);
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
			field.$input?.off('.sirajCoordinates').on('input.sirajCoordinates change.sirajCoordinates', () => {
				update(frm, false);
				resolveFromInputs(frm, cfg);
			});
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

		// Natural Earth land polygons (offline basemap layer). The basemap
		// switcher decides whether this or a tile layer is visible based on
		// the user's last choice (persisted in localStorage).
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (response.ok) {
				const world = await response.json();
				if (states.get(key) === state) {
					state.offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
						style: { color: '#7793a0', weight: 1, fillColor: '#eef3ed', fillOpacity: 1, interactive: false },
					});
					basemap.setOfflineLayer(state.offlineLayer);
					if (state.marker && state.marker.bringToFront) state.marker.bringToFront();
				}
			}
		} catch (err) { console.warn('[SIRAJ] coordinate map: Natural Earth failed:', err && err.message); }
		// Server-managed cached tile layer — same endpoint as Explorer; this
		// becomes the "standard" basemap. Don't addTo(map) yet — the basemap
		// controller decides visibility based on persisted user choice.
		if (states.get(key) === state) {
			try {
				const r = await frappe.call({ method: 'siraj_research.tile_cache.active_layer', type: 'GET' });
				const cfg = (r && r.message) || {};
				if (cfg.layer && cfg.url) {
					const minZ = (cfg.minZoom != null) ? cfg.minZ : 0;
					const maxZ = cfg.maxZoom || 19;
					map.options.minZoom = minZ;
					state.tileLayer = L.tileLayer(cfg.url, {
						minZoom: minZ, maxZoom: maxZ, maxNativeZoom: maxZ,
						attribution: cfg.attribution || '',
					});
					let overlay = null;
					if (cfg.overlayUrl) {
						overlay = L.tileLayer(cfg.overlayUrl, { minZoom:minZ, maxZoom:maxZ, maxNativeZoom:maxZ, pane:'overlayPane' });
					}
					if (cfg.attribution && map.attributionControl) map.attributionControl.addAttribution(cfg.attribution);
					basemap.setStandardLayer(state.tileLayer, overlay);
				} else {
					basemap.setStandardLayer(null, null);
				}
			} catch (e) { console.warn('[SIRAJ] coordinate map: cached tile layer unavailable:', e); basemap.setStandardLayer(null, null); }
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
					[fn](frm2) {
					update(frm2);
					// Manual coordinates must resolve even when the visual map
					// cannot mount (hidden tab, permission-only field, etc.).
					resolveFromInputs(frm2, cfg);
				},
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
		cfgs.forEach(c => {
			mount(frm, c);
			resolveFromInputs(frm, c);
		});
	}

	$(document).on('form-refresh.sirajCoordinates', (_e, frm) => {
		setTimeout(() => mountAllFor(frm), 0);
	});

	// Expose module version + config for Diagnostics.
	window.SIRAJ_COORDINATE_MAP_VERSION = MODULE_VERSION;
	window.SIRAJ_COORDINATE_DOCS_ACTIVE = DEFAULT_COORDS;
	window.SirajCoordinateMap = {
		docConfig, parseCoordinate, resolveAndApply, applyAdminChain,
	};
})();
