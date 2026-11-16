// Mocked Desk form + Leaflet; not a substitute for Frappe/browser integration.
// NODE_PATH=/tmp/siraj-map-test/node_modules node tests/test_coordinate_map.js
const assert = require('assert');
const fs = require('fs');
const {JSDOM} = require('jsdom');
const dom = new JSDOM('<main id="form"></main>', {runScripts:'dangerously', url:'http://example.test/app'});
const w = dom.window, $ = require('jquery')(w);
w.$ = $; w.__ = s => s;
let network = 0, maps = [], registrations = {};
class Map {
  constructor() { this.events = {}; this.layers = []; this.zoom = 4; this.views = []; maps.push(this); }
  setView(point, zoom) { this.views.push(point); this.zoom = zoom; return this; }
  getZoom() { return this.zoom; }
  on(name, handler) { this.events[name] = handler; return this; }
  removeLayer(layer) { this.layers = this.layers.filter(item => item !== layer); }
  invalidateSize() {} remove() { this.removed = true; }
}
class Layer {
  constructor(point) { this.point = point; }
  addTo(map) { map.layers.push(this); this.map = map; return this; }
  setLatLng(point) { this.point = point; }
  bringToFront() {}
}
w.L = {map: () => new Map(), marker: point => new Layer(point), geoJSON: () => new Layer(),
       tileLayer: () => { network++; return new Layer(); }};
w.topojson = {feature: () => ({})};
w.fetch = async () => ({ok:true, json:async () => ({objects:{countries:{}}})});
w.frappe = {require: async () => {}, ui:{form:{on: (doctype, events) => {registrations[doctype] = events;}}}};
w.eval(fs.readFileSync('siraj_research/public/js/coordinate_map.js','utf8'));
function form(doctype, type='Data') {
  const container = $('<div></div>').appendTo('#form');
  const latWrapper = $('<div><input></div>').appendTo(container), lonWrapper = $('<div><input></div>').appendTo(container);
  const lat = {df:{fieldtype:type}, $wrapper:latWrapper, $input:latWrapper.find('input'), status:'Write', get_status(){return this.status;}};
  const lon = {df:{fieldtype:type}, $wrapper:lonWrapper, $input:lonWrapper.find('input'), status:'Write', get_status(){return this.status;}};
  const frm = {doctype, docname:'record', doc:{latitude:'',longitude:''}, fields_dict:{latitude:lat,longitude:lon}, calls:[],
    async set_value(values) { this.calls.push(values); Object.assign(this.doc,values); lat.$input.val(this.doc.latitude); lon.$input.val(this.doc.longitude); }};
  return {frm, lat, lon, container};
}
const wait = () => new Promise(resolve => setTimeout(resolve, 20));
(async () => {
  const x = form('Custom Survey');
  $(w.document).trigger('form-refresh',[x.frm]); await wait();
  assert.equal(maps.length,1); assert.equal(network,0); assert.equal(x.container.find('.siraj-coordinate-map').length,1);
  x.lat.$input.val('٣٣٫١٢٣٤٥٦٧٨٩٠١٢٣٤٥٦').trigger('input');
  x.lon.$input.val('۴۴٫۲۵').trigger('input');
  assert.equal(x.lat.$input.val(),'٣٣٫١٢٣٤٥٦٧٨٩٠١٢٣٤٥٦'); // no rewrite of precision or script
  assert.deepEqual(Array.from(maps[0].views.at(-1)), [33.123456789012344,44.25]);
  maps[0].events.click({latlng:{lat:0,lng:0}}); await wait();
  assert.equal(x.frm.calls.length,1); assert.equal(x.frm.doc.latitude,'0'); assert.equal(x.frm.doc.longitude,'0');
  maps[0].events.click({latlng:{lat:0.0000001,lng:-0.0000002}}); await wait();
  assert.equal(x.frm.doc.latitude,'0.0000001'); assert.equal(x.frm.doc.longitude,'-0.0000002');
  x.lat.$input.val('90.00000000000000001').trigger('input'); assert(x.container.text().includes('Enter valid decimal coordinates'));
  x.lat.$input.val('91').trigger('input'); assert(x.container.text().includes('Enter valid decimal coordinates'));
  const toggle = x.container.find('button').filter((i,e)=>$(e).text()==='Enable online street map');
  toggle.trigger('click'); assert.equal(network,1); toggle.trigger('click');
  $(w.document).trigger('form-refresh',[x.frm]); await wait(); assert.equal(maps.length,1);
  x.lat.status = 'Read'; x.lon.status = 'Read'; $(w.document).trigger('form-refresh',[x.frm]); await wait();
  const before = x.frm.calls.length; maps[0].events.click({latlng:{lat:1,lng:2}}); await wait(); assert.equal(x.frm.calls.length,before);
  assert(x.container.text().includes('read-only'));
  x.lon.status = 'None'; $(w.document).trigger('form-refresh',[x.frm]); await wait(); assert.equal(x.container.find('.siraj-coordinate-map').length,0); assert(maps[0].removed);
  const y = form('Numeric Other App','Float'); $(w.document).trigger('form-refresh',[y.frm]); await wait();
  maps[1].events.click({latlng:{lat:1,lng:2}}); await wait(); assert.equal(y.frm.calls.length,0); assert(y.container.text().includes('Preview only'));
  const z = form('Text Other App','Small Text'); $(w.document).trigger('form-refresh',[z.frm]); await wait();
  maps[2].events.click({latlng:{lat:1,lng:2}}); await wait(); assert.equal(z.frm.doc.latitude,'1');
  z.lat.df.length = 3; maps[2].events.click({latlng:{lat:12.34,lng:2}}); await wait(); assert.equal(z.frm.calls.length,1);
  assert(registrations['Custom Survey']); assert(registrations['Numeric Other App']);
  console.log('Coordinate map: text precision, multilingual input, click, validation, permissions, cleanup, and tile opt-in passed');
})().catch(err=>{console.error(err);process.exitCode=1;});
