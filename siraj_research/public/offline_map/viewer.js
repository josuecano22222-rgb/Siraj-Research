/* Offline-only viewer. No records, network services or persistent storage. */
(() => {
    'use strict';
    const c = window.SIRAJ_OFFLINE_MAP;
    const el = id => document.getElementById(id);
    const messages = {
        en: {language:'Language', mode:'Click mode', basemapLabel:'Basemap', raster:'Raster', vector:'Natural Earth Vector', point:'Point', distance:'Distance', area:'Area', undo:'Undo point', clear:'Clear', lat:'Latitude', lon:'Longitude', go:'Go', fit:'Fit area',
            hint:'Basemap imagery only; no SIRAJ records. Click the map to select or measure.', initial:'Tiles are available only where included in this package.', invalid:'Enter decimal latitude from −85.05112878 to 85.05112878 and longitude from −180 to 180.',
            selected:'Latitude: {0}, longitude: {1}', length:'Approximate distance: {0} km ({1} points)', surface:'Approximate area: {0} km² ({1} points)', need2:'Click at least two points to measure distance.', need3:'Click at least three points to measure area.', maximum:'The measurement is limited to 500 points.', offline:'Offline map'},
        ar: {language:'اللغة', mode:'وضع النقر', basemapLabel:'الخيار', raster:'صوري', vector:'متجهات الأرض الطبيعية', point:'نقطة', distance:'المسافة', area:'المساحة', undo:'التراجع عن نقطة', clear:'مسح', lat:'خط العرض', lon:'خط الطول', go:'انتقال', fit:'عرض المنطقة',
            hint:'صور الخريطة فقط؛ لا تتضمن سجلات سراج. انقر لتحديد نقطة أو للقياس.', initial:'تتوفر مربعات الخريطة فقط حيث تتضمنها الحزمة.', invalid:'أدخل خط عرض عشرياً بين −85.05112878 و85.05112878 وخط طول بين −180 و180.',
            selected:'خط العرض: {0}، خط الطول: {1}', length:'المسافة التقريبية: {0} كم ({1} نقطة)', surface:'المساحة التقريبية: {0} كم² ({1} نقطة)', need2:'انقر نقطتين على الأقل لقياس المسافة.', need3:'انقر ثلاث نقاط على الأقل لقياس المساحة.', maximum:'القياس محدود بـ 500 نقطة.', offline:'خريطة دون اتصال'}
    };
    let lang = 'en', points = [], shape = null;
    const t = (key, ...args) => messages[lang][key].replace(/\{(\d+)\}/g, (_, i) => args[i]);
    const map = L.map('map', {minZoom: c.minzoom, maxZoom: c.maxzoom}).setView(c.center, c.minzoom);
    const attribution = document.createElement('span');
    attribution.textContent = c.attribution;
    const tileLayer = L.tileLayer('tiles/{z}/{x}/{y}.' + c.extension, {minZoom: c.minzoom, maxZoom: c.maxzoom,
        attribution: attribution.innerHTML}).addTo(map);
    L.control.scale({imperial: false}).addTo(map);
    /* Natural Earth Vector basemap (bundled 1:110m tier, public domain).
     * Loaded from the app's static assets so it works fully offline. */
    const NE_BASE = '/assets/siraj_research/natural_earth/110m';
    const NE_ROLES = [
        ['ocean', 'ne_110m_ocean.geojson', {style:{color:'#d4e4f0', fillColor:'#d4e4f0', fillOpacity:0.9}}],
        ['land', 'ne_110m_land.geojson', {style:{color:'#7a6a4f', fillColor:'#e8e4cf', fillOpacity:1}}],
        ['lakes', 'ne_110m_lakes.geojson', {style:{color:'#5b8db8', fillColor:'#5b8db8', fillOpacity:0.8}}],
        ['countries', 'ne_110m_admin_0_countries.geojson', {style:{color:'#7a6a4f', fillColor:'#d9d0b8', fillOpacity:0.6}}],
        ['boundaries', 'ne_110m_admin_0_boundary_lines_land.geojson', {style:{color:'#7a6a4f', weight:0.6}}],
        ['admin1', 'ne_110m_admin_1_states_provinces_lines.geojson', {style:{color:'#9a8b6e', weight:0.4, dashArray:'2 1'}}],
        ['rivers', 'ne_110m_rivers_lake_centerlines.geojson', {style:{color:'#5b8db8', weight:0.6}}],
        ['places', 'ne_110m_populated_places_simple.geojson', {}],
    ];
    const neGroups = {};
    async function setBasemap(mode) {
        if (mode === 'raster') {
            Object.values(neGroups).forEach(g => map.removeLayer(g));
            if (!map.hasLayer(tileLayer)) tileLayer.addTo(map);
            map.attributionControl.setAttribution(c.attribution);
            return;
        }
        if (map.hasLayer(tileLayer)) map.removeLayer(tileLayer);
        map.attributionControl.setAttribution('Natural Earth Vector (public domain)');
        for (const [role, file, styleCfg] of NE_ROLES) {
            if (neGroups[role]) continue;
            try {
                const res = await fetch(NE_BASE + '/' + file);
                if (!res.ok) continue;
                const gj = await res.json();
                const cfg = Object.assign({}, styleCfg);
                if (role === 'places') {
                    cfg.pointToLayer = (feature, latlng) => L.circleMarker(latlng, {radius: 2, color: '#555', fillColor: '#555'});
                    cfg.onEachFeature = (feature, layer) => {
                        if (feature.properties && feature.properties.name) layer.bindPopup('<b>' + feature.properties.name + '</b>');
                    };
                }
                neGroups[role] = L.geoJSON(gj, cfg).addTo(map);
            } catch (_) { /* layer optional */ }
        }
    }
    el('basemap').addEventListener('change', () => setBasemap(el('basemap').value));
    const limit = 85.0511287798066;
    function number(text) {
        const normalized = text.trim().replace(/[٠-٩]/g, n => String(n.charCodeAt(0) - 0x660))
            .replace(/[۰-۹]/g, n => String(n.charCodeAt(0) - 0x6f0)).replace(/٫/g, '.').replace(/−/g, '-');
        return /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized) ? Number(normalized) : NaN;
    }
    function area(vertices) {
        const rad = Math.PI / 180, radius = 6371008.8;
        let sum = 0;
        vertices.forEach((p, i) => {
            const q = vertices[(i + 1) % vertices.length];
            const delta = ((q.lng - p.lng + 180) % 360 + 360) % 360 - 180;
            sum += delta * rad * (2 + Math.sin(p.lat * rad) + Math.sin(q.lat * rad));
        });
        return Math.abs(sum) * radius * radius / 2;
    }
    function redraw() {
        if (shape) { map.removeLayer(shape); shape = null; }
        if (!points.length) { el('status').textContent = t('initial'); return; }
        const mode = el('mode').value;
        if (mode === 'point') {
            const p = points[0];
            shape = L.circleMarker(p, {radius: 6}).addTo(map);
            el('status').textContent = t('selected', p.lat.toFixed(7), p.lng.toFixed(7));
        } else if (mode === 'distance') {
            shape = L.polyline(points, {color:'#1769aa'}).addTo(map);
            const meters = points.slice(1).reduce((sum, p, i) => sum + map.distance(points[i], p), 0);
            el('status').textContent = points.length < 2 ? t('need2') : t('length', (meters / 1000).toFixed(3), points.length);
        } else {
            shape = L.polygon(points, {color:'#1769aa'}).addTo(map);
            el('status').textContent = points.length < 3 ? t('need3') : t('surface', (area(points) / 1e6).toFixed(3), points.length);
        }
    }
    function setLanguage() {
        lang = el('language').value === 'ar' ? 'ar' : 'en';
        document.documentElement.lang = lang;
        document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
        for (const [id, key] of Object.entries({languageLabel:'language', modeLabel:'mode', basemapLabel:'basemapLabel', undo:'undo', clear:'clear', latLabel:'lat', lonLabel:'lon', go:'go', fit:'fit', hint:'hint'})) el(id).textContent = t(key);
        for (const option of el('basemap').options) option.textContent = t(option.value === 'vector' ? 'vector' : 'raster');
        for (const option of el('mode').options) option.textContent = t(option.value);
        el('map').setAttribute('aria-label', t('offline'));
        redraw();
    }
    map.on('click', e => {
        if (points.length >= 500 && el('mode').value !== 'point') { el('status').textContent = t('maximum'); return; }
        const p = {lat:e.latlng.lat, lng:((e.latlng.lng + 180) % 360 + 360) % 360 - 180};
        if (el('mode').value === 'point') points = [p];
        else {
            if (points.length) {
                const prev = points[points.length - 1].lng;
                p.lng = prev + ((p.lng - prev + 180) % 360 + 360) % 360 - 180;
            }
            points.push(p);
        }
        redraw();
    });
    el('mode').addEventListener('change', () => { points = []; redraw(); });
    el('language').addEventListener('change', setLanguage);
    el('undo').addEventListener('click', () => { points.pop(); redraw(); });
    el('clear').addEventListener('click', () => { points = []; redraw(); });
    el('go').addEventListener('click', () => {
        const lat = number(el('lat').value), lon = number(el('lon').value);
        if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > limit || Math.abs(lon) > 180) { el('status').textContent = t('invalid'); return; }
        points = [{lat, lng:lon}];
        el('mode').value = 'point';
        map.setView([lat, lon], Math.min(c.maxzoom, Math.max(c.minzoom, map.getZoom())));
        redraw();
    });
    el('fit').addEventListener('click', () => {
        // East may exceed 180 when the selected area crosses the antimeridian.
        const b = c.bounds, east = b[2] < b[0] ? b[2] + 360 : b[2];
        map.fitBounds([[b[1], b[0]], [b[3], east]], {padding:[10, 10], maxZoom:c.maxzoom});
    });
    setLanguage();
})();
