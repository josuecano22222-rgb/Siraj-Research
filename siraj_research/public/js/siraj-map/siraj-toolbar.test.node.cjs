/* Node regression test for toolbar icon rendering.
 * Loads the same modules the browser loads and exercises the toolbar's
 * _addButton path, asserting every rendered <svg> differs from the fallback
 * Source glyph and matches what sirajIcons.toolSvg(key) produces.
 *
 * Run: node public/js/siraj-map/siraj-toolbar.test.node.cjs
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '../../..');

// --- Minimal DOM/L stubs ---
function makeEl(tag, cls, parent) {
  const el = {
    tagName: tag.toUpperCase(),
    className: cls || '',
    children: [],
    attrs: {},
    _style: {},
    _html: '',
    _events: {},
    classList: {
      _s: new Set(),
      add(c) { c.split(/\s+/).forEach(x=>x && this._s.add(x)); el.className = [...this._s].join(' '); },
      remove(c) { c.split(/\s+/).forEach(x=>this._s.delete(x)); el.className = [...this._s].join(' '); },
      toggle(c, on) { if (on===undefined) on=!this._s.has(c); on ? this.add(c) : this.remove(c); return on; },
      contains(c) { return this._s.has(c); },
    },
    appendChild(c) { el.children.push(c); if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = el; return c; },
    removeChild(c) { const i = el.children.indexOf(c); if (i>=0) el.children.splice(i,1); return c; },
    setAttribute(k,v) { el.attrs[k] = String(v); },
    getAttribute(k) { return el.attrs[k]; },
    addEventListener(ev, fn) { (el._events[ev] = el._events[ev] || []).push(fn); },
    set innerHTML(html) { el._html = html; el.children = []; },
    get innerHTML() { return el._html; },
    querySelectorAll() { return []; },
    get style() { return new Proxy({}, { set: (t,k,v) => { el._style[k]=v; return true; }, get:(t,k)=>el._style[k]||''}); },
  };
  return el;
}
const L = {
  Util: { setOptions(o,a){ Object.assign(o,a||{}); return o; } },
  DomUtil: {
    create(tag, cls, parent){ const e=makeEl(tag,cls); if(parent)parent.appendChild(e); return e; },
  },
  DomEvent: {
    on(el, ev, fn) { el.addEventListener ? el.addEventListener(ev,fn) : null; },
    off(){}, stopPropagation(){}, disableClickPropagation(){}, disableScrollPropagation(){},
  },
  Control: { extend(obj) {
    function Ctor(o){ this.options={position:'topright'}; this._groups=[]; this._buttons=new Map(); this.initialize(o); }
    Ctor.prototype = Object.assign({
      initialize(options){ L.Util.setOptions(this,options||{}); this._groups=[]; this._current=null; this._buttons=new Map(); },
      onAdd(map){ this._map=map; this._container=makeEl('div','siraj-toolbar leaflet-bar'); return this._container; },
    }, obj);
    return Ctor;
  }},
  control: { sirajToolbar: options => new L.Control.SirajToolbar(options) },
};
const mapStub = { on(){}, off(){}, getContainer:()=>makeEl('div') };

function makeCtx() {
  const sandbox = {
    window:{}, console, setTimeout, document:{createElement:makeEl, body:makeEl('body')},
    frappe:{_:s=>s, ui:{}, boot:{siraj_record_meta:{colours:{},glyphs:{}}}},
    btoa: s=>Buffer.from(s,'binary').toString('base64'), atob:s=>Buffer.from(s,'base64').toString('binary'),
    localStorage:{_d:{},getItem(k){return this._d[k]||null;},setItem(k,v){this._d[k]=v;},removeItem(k){delete this._d[k];}},
  };
  sandbox.window.L = L; sandbox.L = L;
  sandbox.__ = s=>s;
  sandbox.encodeURIComponent=encodeURIComponent; sandbox.decodeURIComponent=decodeURIComponent;
  sandbox.escape=escape; sandbox.unescape=unescape;
  vm.createContext(sandbox);
  // Load modules in bundle order.
  for (const rel of [
    'public/js/siraj-record-meta.js',
    'public/js/siraj-map/siraj-graph.js',
    'public/js/siraj-map/siraj-filters.js',
    'public/js/siraj-map-kit.js',
    'public/js/siraj-map-toolbar.js',
  ]) vm.runInContext(fs.readFileSync(path.join(ROOT, rel),'utf8'), sandbox);
  return sandbox;
}

function assert(c,m){ if(!c){console.error('FAIL:',m);process.exit(1);} console.log(' ok -',m); }

function run() {
  const sb = makeCtx();
  const si = sb.window.sirajIcons;
  assert(si && si.tools && si.toolSvg, 'sirajIcons.tools/toolSvg exist');

  // Source glyph = the fallback record document glyph.
  const sourceSvg = si.svg('Source',{size:18});
  assert(sourceSvg.indexOf('M6 3h9l3 3v15H6Z') >= 0, 'Source glyph contains the document path (sanity)');

  // Build a toolbar and add every TOOL_SPEC entry exactly as Explorer would.
  const toolbar = new sb.L.Control.SirajToolbar({position:'topright'});
  toolbar.onAdd(mapStub);
  const spec = sb.window.SirajMapKit.TOOL_SPEC;
  const bad = [];
  const seenMarkup = new Map();
  spec.forEach(s => {
    const btn = toolbar._addButton({items:[]}, s);
    // Look for the <svg> markup in btn._html.
    const m = /<svg[^>]*class="([^"]*)"[^>]*>([\s\S]*?)<\/svg>/.exec(btn._html);
    if (!m) { bad.push(s.id+': no svg rendered'); return; }
    const cls = m[1];
    const inner = m[2];
    if (inner.indexOf('M6 3h9l3 3v15H6Z') >= 0) { bad.push(s.id+': rendered fallback Source glyph (icon key "'+s.icon+'" not found in TOOLS)'); return; }
    const clsCheck = new RegExp('siraj-ico-' + s.icon.replace(/[-\/\\^$*+?.()|[\]{}]/g,'\\$&'));
    if (!clsCheck.test(cls)) { bad.push(s.id+': svg class missing siraj-ico-'+s.icon+' (got "'+cls+'")'); }
    if (!btn.getAttribute('aria-label')) { bad.push(s.id+': missing aria-label'); }
    if (!btn.title) { bad.push(s.id+': missing title'); }
    // Duplicate markup check.
    if (seenMarkup.has(inner) && s.icon !== 'clear') {
      // 'clear' measurement and 'eraser' selection are intentionally similar but different keys; skip them.
      // still mark if same icon key:
      if (seenMarkup.get(inner) !== s.icon) bad.push(s.id+': duplicate SVG as '+seenMarkup.get(inner));
    } else seenMarkup.set(inner, s.icon);
  });
  assert(bad.length === 0, bad.length ? bad.join('\n       ') : 'every TOOL_SPEC button renders its own tool icon (no Source fallback, classes correct, aria+title set, no duplicates)');
  assert(spec.length >= 25, 'TOOL_SPEC has at least 25 entries, got '+spec.length);
  console.log('\nAll siraj-toolbar tests passed ('+spec.length+' tools).');
}
run();
