/* Universal administrative-hierarchy client.
 *
 * One implementation backs Desk forms (Person, Institution, Place, events,
 * units, deployments), the Siraj Explorer map, and manual coordinate fields.
 * Server resolution is authoritative and creates/reuses hierarchy records;
 * the offline geo worker is a fallback so the chain still appears without a
 * connection. Missing levels are shown as gaps, never invented.
 */
(() => {
  'use strict';
  const t = s => (typeof __ === 'function' ? __(s) : s);
  const CHAIN = ['country', 'governorate', 'district', 'municipality', 'village', 'community'];
  const cache = new Map();
  const inflight = new Map();
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  function key(lat, lon, createMissing, useOnline) {
    return [Number(lat).toFixed(5), Number(lon).toFixed(5), !!createMissing, !!useOnline].join('|');
  }

  async function fromWorker(lat, lon) {
    if (!window.SirajGeo || !window.SirajGeo.resolve) return null;
    try { return await window.SirajGeo.resolve(lat, lon); } catch (_) { return null; }
  }

  // Convert an offline resolver payload to the same shape as hierarchy_for_point.
  function normaliseOffline(raw, lat, lon) {
    const levels = CHAIN.map((field, level) => {
      const node = raw && raw.admin_chain && raw.admin_chain[field];
      const label = node && (node.name_ar || node.name_en);
      return {
        level, field,
        doctype: field === 'country' ? 'Country' : field[0].toUpperCase() + field.slice(1),
        label: field[0].toUpperCase() + field.slice(1),
        label_ar: field,
        name: null,
        label_en: node && node.name_en ? node.name_en : null,
        label_ar_value: node && node.name_ar ? node.name_ar : null,
        code: node && node.pcode ? node.pcode : null,
        confidence: 'medium',
        source: 'offline-worker',
        status: label ? 'resolved' : 'gap',
      };
    });
    const place = raw && raw.nearest_place;
    const result = {
      lat, lon, levels,
      by_field: Object.fromEntries(levels.map(r => [r.field, r])),
      gaps: levels.filter(r => r.status === 'gap'),
      nearest_place: place || null,
      nearest_place_name: place && (place.name_ar || place.name_en) || null,
      warnings: (raw && raw.warnings) || [],
      provenance: ['offline-worker'],
      ambiguous: !!(raw && raw.ambiguous),
      on_land: !!(raw && raw.on_land),
      source: 'offline',
      resolved_count: levels.filter(r => r.status !== 'gap').length,
      deepest_level: Math.max(-1, ...levels.filter(r => r.status !== 'gap').map(r => r.level)),
    };
    result.text_en = formatChain(result, 'en');
    result.text_ar = formatChain(result, 'ar');
    return result;
  }

  function formatChain(result, lang) {
    return (result.levels || []).map(r => (
      (lang === 'ar' ? (r.label_ar_value || r.label_ar) : (r.label_en || r.label)) || '—'
    )).join(' › ');
  }

  async function resolve(lat, lon, opts = {}) {
    const createMissing = opts.createMissing !== false;
    const useOnline = !!opts.useOnline;
    const k = key(lat, lon, createMissing, useOnline);
    if (cache.has(k)) return cache.get(k);
    if (inflight.has(k)) return inflight.get(k);
    const job = (async () => {
      let result = null;
      if (!opts.offlineOnly) {
        try {
          result = await frappe.xcall('siraj_research.geo_hierarchy_ui.hierarchy_for_point', {
            latitude: Number(lat), longitude: Number(lon),
            create_missing: createMissing ? 1 : 0, use_online: useOnline ? 1 : 0,
          });
        } catch (_) { result = null; }
      }
      if (!result || result.error) {
        const offline = await fromWorker(lat, lon);
        if (offline) result = normaliseOffline(offline, lat, lon);
      }
      if (!result || result.error) {
        result = {
          lat, lon, levels: [], by_field: {}, gaps: [], warnings: ['unresolved'],
          source: 'none', resolved_count: 0, deepest_level: -1, text_en: '', text_ar: '',
        };
      }
      result.source = result.source || 'server';
      cache.set(k, result);
      return result;
    })();
    inflight.set(k, job);
    try { return await job; } finally { inflight.delete(k); }
  }

  function render(target, result, opts = {}) {
    if (!target) return;
    try {
    const $box = target.jquery ? target : $(target);
    $box.empty().addClass('siraj-hierarchy').attr('data-hierarchy-build', window.SIRAJ_BUILD || '');
    const levels = result.levels || [];
    const head = $('<div class="siraj-hierarchy-head"></div>').appendTo($box);
    $('<strong></strong>').text(t('Administrative hierarchy')).appendTo(head);
    if (result.source === 'offline') {
      $('<span class="label label-warning"></span>').text(t('offline')).appendTo(head);
    } else if (result.source === 'online') {
      $('<span class="label label-warning"></span>').text(t('online fallback')).appendTo(head);
    }
    const actions = $('<span class="siraj-hierarchy-actions"></span>').appendTo(head);
    $('<button type="button" class="btn btn-default btn-xs"></button>')
      .text(t('Copy')).on('click', () => {
        const text = result.text_en || formatChain(result, 'en');
        if (navigator.clipboard) navigator.clipboard.writeText(text);
      }).appendTo(actions);
    if (opts.refresh) {
      $('<button type="button" class="btn btn-default btn-xs"></button>')
        .text(t('Refresh')).on('click', opts.refresh).appendTo(actions);
    }

    const chain = $('<div class="siraj-hierarchy-chain"></div>').appendTo($box);
    levels.forEach(row => {
      const $level = $('<div class="siraj-level"></div>')
        .addClass(row.status === 'gap' ? 'is-gap' : '')
        .addClass(row.confidence === 'medium' ? 'is-online' : '')
        .attr('data-field', row.field || '');
      $('<span class="siraj-level-label"></span>')
        .text(row.label_ar || row.label).appendTo($level);
      const label = row.label_en || row.label_ar_value || row.code || '—';
      if (row.doctype && row.name) {
        $('<a class="siraj-level-value" href="#"></a>').text(label)
          .attr('title', `${row.doctype}: ${row.name}`)
          .on('click', ev => {
            ev.preventDefault();
            frappe.set_route('Form', row.doctype, row.name);
          }).appendTo($level);
      } else {
        $('<span class="siraj-level-value"></span>').text(label).appendTo($level);
      }
      if (row.code) $('<span class="siraj-level-code"></span>').text(row.code).appendTo($level);
      chain.append($level);
    });
    if (result.nearest_place_name) {
      $('<div class="siraj-hierarchy-summary"></div>')
        .text(`${t('Nearest place')}: ${result.nearest_place_name}`).appendTo($box);
    }
    if ((result.warnings || []).length) {
      $('<div class="siraj-hierarchy-warnings"></div>')
        .text(result.warnings.map(w => t(String(w).replace(/_/g, ' '))).join(' · '))
        .appendTo($box);
    }
    return $box;
    } catch (err) {
      console.warn('[SIRAJ hierarchy] render failed:', err && err.message);
      return target && target.jquery ? target : $(target);
    }
  }

  // Desk form integration: one panel per [frm, lat field, lon field].
  const formPanels = new WeakMap();
  async function refreshForm(frm, cfg, lat, lon, opts = {}) {
    if (!frm || !cfg || lat == null || lon == null) return null;
    const latField = frm.fields_dict && frm.fields_dict[cfg.lat_field];
    const lonField = frm.fields_dict && frm.fields_dict[cfg.lon_field];
    if (!latField || !lonField) return null;
    let panel = formPanels.get(frm);
    if (!panel || panel.attr('data-fields') !== `${cfg.lat_field}:${cfg.lon_field}`) {
      const $section = lonField.$wrapper.closest('.form-section').find('.section-body').first();
      panel = $('<div class="siraj-form-hierarchy"></div>')
        .attr('data-fields', `${cfg.lat_field}:${cfg.lon_field}`);
      if ($section.length) $section.append(panel);
      else lonField.$wrapper.after(panel);
      formPanels.set(frm, panel);
    }
    const result = await resolve(lat, lon, opts);
    render(panel, result, { refresh: () => refreshForm(frm, cfg, lat, lon, { ...opts, force: true }) });
    return result;
  }

  function showPoint(latlng, opts = {}) {
    const lat = Number(latlng.lat), lon = Number(latlng.lng);
    const dlg = new frappe.ui.Dialog({
      title: t('Administrative hierarchy at this point'),
      fields: [{ fieldtype: 'HTML', fieldname: 'hierarchy' }],
      primary_action_label: t('Close'),
      primary_action: () => dlg.hide(),
    });
    const body = $(dlg.fields_dict.hierarchy.$wrapper).find('.like-disabled-input');
    const target = body.length ? body : $(dlg.body);
    target.html('<div class="siraj-hierarchy-loading">' + t('Resolving hierarchy…') + '</div>');
    dlg.show();
    resolve(lat, lon, opts).then(result => render(target, result));
    return dlg;
  }

  function showCoordinateDialog() {
    const dlg = new frappe.ui.Dialog({
      title: t('Resolve coordinates to hierarchy'),
      fields: [
        { fieldname: 'latitude', label: t('Latitude'), fieldtype: 'Float', reqd: 1,
          description: t('Accepts eastern-Arabic digits and decimal notation.') },
        { fieldname: 'longitude', label: t('Longitude'), fieldtype: 'Float', reqd: 1 },
        { fieldname: 'hierarchy', fieldtype: 'HTML' },
      ],
      primary_action_label: t('Resolve'),
      primary_action: values => {
        const lat = Number(values.latitude), lon = Number(values.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const target = $(dlg.fields_dict.hierarchy.$wrapper).find('.like-disabled-input');
        resolve(lat, lon, { force: true }).then(r => render(target.length ? target : $(dlg.body), r));
      },
    });
    dlg.show();
    return dlg;
  }

  window.SirajHierarchy = {
    resolve, render, formatChain, refreshForm, showPoint, showCoordinateDialog,
    clearCache: () => cache.clear(),
  };
})();
