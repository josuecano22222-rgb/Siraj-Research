/* Client-side bounded export of already-authorized local raster tiles only. */
(() => {
    'use strict';
    const LIMIT = 512, MAX_BYTES = 16 * 1024 * 1024, MAX_TILE_BYTES = 4 * 1024 * 1024, LAT = 85.0511287798066;
    const assets = ['offline_map/index.html', 'offline_map/viewer.js', 'offline_map/records.js', 'vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css', 'vendor/leaflet/LICENSE',
        'vendor/leaflet/images/layers.png', 'vendor/leaflet/images/layers-2x.png', 'vendor/leaflet/images/marker-icon.png', 'vendor/leaflet/images/marker-icon-2x.png', 'vendor/leaflet/images/marker-shadow.png'];
    const y = (lat,n) => (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n;
    function plan(bounds, min, max) {
        if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(Number.isFinite) ||
            !Number.isInteger(min) || !Number.isInteger(max) || min < 0 || max > 22 || min > max) throw Error('invalid');
        const [west, south, east, north] = bounds;
        if (west < -180 || west > 180 || east < -180 || east > 180 || west === east || south < -LAT || north > LAT || south >= north) throw Error('invalid');
        const ranges = []; let count = 0;
        for (let z = min; z <= max; z++) {
            const n = 2 ** z, clamp = v => Math.max(0, Math.min(n-1, v));
            const y0 = clamp(Math.floor(y(north,n))), y1 = clamp(Math.ceil(y(south,n)) - 1);
            const segments = west < east ? [[west,east]] : [[west,180],[-180,east]];
            let columns = segments.filter(([a,b]) => a < b).map(([a,b]) => [clamp(Math.floor((a+180)/360*n)), clamp(Math.ceil((b+180)/360*n)-1)]).sort((a,b)=>a[0]-b[0]);
            if (columns.length === 2 && columns[1][0] <= columns[0][1]+1) columns = [[columns[0][0], Math.max(columns[0][1], columns[1][1])]];
            for (const [x0,x1] of columns) {
                if (x1 < x0 || y1 < y0) continue;
                count += (x1-x0+1)*(y1-y0+1);
                if (count > LIMIT) throw Error('limit');
                ranges.push({z,x0,x1,y0,y1});
            }
        }
        if (!count) throw Error('invalid');
        return {ranges,count};
    }
    async function build(pack, bounds, min, max, signal, progress) {
        if (!pack || !pack.download_allowed || !['standard','aerial'].includes(pack.kind) ||
            !['png','jpg','jpeg','webp'].includes(pack.format) || min < pack.minzoom || max > pack.maxzoom) throw Error('invalid');
        const selection = plan(bounds,min,max), zip = new JSZip(), extension = pack.format === 'jpeg' ? 'jpg' : pack.format;
        let done = 0, stored = 0, bytes = 0;
        for (const range of selection.ranges) for (let x=range.x0; x<=range.x1; x++) for (let y=range.y0; y<=range.y1; y++) {
            const url = '/api/method/siraj_research.local_maps.tile?kind=' + encodeURIComponent(pack.kind) + '&z=' + range.z + '&x=' + x + '&y=' + y;
            const response = await fetch(url, {credentials:'same-origin', cache:'no-store', signal});
            if (response.status !== 404) {
                if (!response.ok) throw Error('tile');
                const tile = await response.arrayBuffer();
                bytes += tile.byteLength;
                if (!tile.byteLength || tile.byteLength > MAX_TILE_BYTES || bytes > MAX_BYTES) throw Error('size');
                zip.file(`tiles/${range.z}/${x}/${y}.${extension}`, tile, {compression:'STORE'}); stored++;
            }
            progress(++done, selection.count, stored);
        }
        if (!stored) throw Error('empty');
        for (const asset of assets) {
            const response = await fetch('/assets/siraj_research/' + asset, {credentials:'same-origin', cache:'no-store', signal});
            if (!response.ok) throw Error('asset');
            const name = asset.replace(/^offline_map\//,'').replace(/^vendor\/leaflet\//,'leaflet/');
            const data = await response.arrayBuffer();
            if (data.byteLength > 2 * 1024 * 1024) throw Error('asset');
            zip.file(name, data, {compression:'DEFLATE'});
        }
        const [west,south,east,north] = bounds, span = east > west ? east-west : (east-west+360)%360;
        const center = [(south+north)/2, ((west+span/2+180)%360+360)%360-180];
        zip.file('config.js', 'window.SIRAJ_OFFLINE_MAP = ' + JSON.stringify({minzoom:min,maxzoom:max,center,bounds,extension,attribution:pack.attribution || ''}) + ';\n');
        if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
        const blob = await zip.generateAsync({type:'blob'});
        if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
        return {blob, stored, requested:selection.count, bytes};
    }
    window.sirajOfflineDownload = {plan, build, limit:LIMIT};
})();
