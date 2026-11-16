// npm install --prefix /tmp/siraj-map-test --no-save jsdom@24
// NODE_PATH=/tmp/siraj-map-test/node_modules node tests/test_offline_viewer.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');
const dir = path.resolve(__dirname, '../siraj_research/public/offline_map');
const dom = new JSDOM(fs.readFileSync(path.join(dir, 'index.html'), 'utf8'), {runScripts:'outside-only'});
const w = dom.window, d = w.document;
let click, shape, fit;
const layer = points => ({points, addTo() { shape = this; return this; }});
const map = {setView() {return this;}, getZoom() {return 3;}, on(name, fn) {if (name === 'click') click = fn;},
  removeLayer() {}, fitBounds(bounds) {fit = bounds;},
  distance(a, b) {const rad=Math.PI/180, h=Math.sin((a.lat-b.lat)*rad/2)**2 + Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin((a.lng-b.lng)*rad/2)**2;return 6371008.8*2*Math.asin(Math.sqrt(h));}};
w.L = {map:()=>map, tileLayer:()=>layer(), circleMarker:layer, polyline:layer, polygon:layer, control:{scale:()=>layer()}};
w.SIRAJ_OFFLINE_MAP = {minzoom:0, maxzoom:12, center:[0,180], bounds:[170,-10,-170,10], extension:'png', attribution:'<img src=x>'};
w.eval(fs.readFileSync(path.join(dir, 'viewer.js'), 'utf8'));
const change = (id, val) => {d.getElementById(id).value=val;d.getElementById(id).dispatchEvent(new w.Event('change'));};
const point = (lat,lng) => click({latlng:{lat,lng}});
const status = () => d.getElementById('status').textContent;
change('mode','distance'); point(0,179); point(0,-179);
assert(Math.abs(parseFloat(status().match(/distance: ([\d.]+)/)[1]) - 222.39) < 0.1);
assert.equal(shape.points[1].lng,181); // draw the short dateline crossing
change('mode','area'); [[0,0],[0,1],[1,1],[1,0]].forEach(([a,b])=>point(a,b));
assert(Math.abs(parseFloat(status().match(/area: ([\d.]+)/)[1]) - 12363.7) < 10);
d.getElementById('undo').click(); assert(status().includes('(3 points)'));
d.getElementById('clear').click(); assert(status().includes('available only'));
d.getElementById('lat').value='۹۱'; d.getElementById('lon').value='٤٤'; d.getElementById('go').click(); assert(status().includes('Enter decimal'));
d.getElementById('lat').value='٣٣٫٣'; d.getElementById('go').click(); assert(status().includes('33.3000000'));
d.getElementById('fit').click(); assert.equal(fit[1][1],190);
change('language','ar'); assert.equal(d.documentElement.dir,'rtl'); assert(status().includes('خط العرض'));
console.log('Offline viewer math: dateline, distance, area, validation and Arabic input passed');
