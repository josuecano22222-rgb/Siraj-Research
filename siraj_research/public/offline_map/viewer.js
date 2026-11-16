/* Offline-only viewer. It never fetches tiles from a network provider. */
(() => {
    const c = window.SIRAJ_OFFLINE_MAP;
    const status = document.getElementById('status');
    const map = L.map('map', {minZoom: c.minzoom, maxZoom: c.maxzoom}).setView(c.center, c.minzoom);
    const text = document.createElement('span');
    text.textContent = c.attribution;
    L.tileLayer('tiles/{z}/{x}/{y}.' + c.extension, {minZoom: c.minzoom, maxZoom: c.maxzoom,
        attribution: text.innerHTML}).addTo(map);
    L.control.scale({imperial: false}).addTo(map);
    let marker;
    map.on('click', e => {
        if (marker) map.removeLayer(marker);
        marker = L.circleMarker(e.latlng, {radius: 6}).addTo(map);
        status.textContent = 'Latitude: ' + e.latlng.lat.toFixed(7) + ', longitude: ' + e.latlng.lng.toFixed(7);
    });
})();
