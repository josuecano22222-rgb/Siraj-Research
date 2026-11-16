// Real Chromium file:// smoke test, no Frappe or real imagery.
// npm install --prefix /tmp/siraj-browser --no-save puppeteer-core@24.2.0 @sparticuz/chromium@133.0.0
// NODE_PATH=/tmp/siraj-browser/node_modules node tests/test_offline_viewer_browser.js
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {pathToFileURL} = require('url');
const {execFileSync} = require('child_process');
const puppeteer = require('puppeteer-core');
const root = path.resolve(__dirname, '..');

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'siraj-viewer-test-'));
  let browser;
  try {
    execFileSync('python3', ['-c', `
import base64, sqlite3, sys, zipfile
from pathlib import Path
from siraj_research.utils.offline_viewer import create_package
p = Path(sys.argv[1]); src = p / 's.mbtiles'
with sqlite3.connect(src) as db:
 db.execute('CREATE TABLE metadata (name TEXT, value TEXT)')
 db.executemany('INSERT INTO metadata VALUES (?,?)', [('format','png'), ('attribution','<img src=x onerror=alert(1)>')])
 db.execute('CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)')
 db.execute('INSERT INTO tiles VALUES (0,0,0,?)', (base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/a3sAAAAASUVORK5CYII='),))
create_package(src, p / 'map.zip', (-180,-85,180,85), 0, 0, redistribution_allowed=True)
with zipfile.ZipFile(p / 'map.zip') as z: z.extractall(p / 'map')
`, tmp], {cwd: root});
    const chromium = require('@sparticuz/chromium');
    const bin = process.env.CHROME_PATH || await chromium.executablePath();
    const dir = path.dirname(require.resolve('@sparticuz/chromium/package.json'));
    const libs = await require(path.join(dir, 'build/lambdafs.js')).default.inflate(path.join(dir, 'bin/al2023.tar.br'));
    process.env.LD_LIBRARY_PATH = path.join(libs, 'lib') + ':' + (process.env.LD_LIBRARY_PATH || '');
    browser = await puppeteer.launch({executablePath: bin, args: ['--no-sandbox', '--disable-setuid-sandbox'], headless: true});
    const page = await browser.newPage();
    const external = [], errors = [];
    page.on('request', request => { if (!request.url().startsWith('file:')) external.push(request.url()); });
    page.on('pageerror', error => errors.push(String(error)));
    await page.setViewport({width: 800, height: 600});
    await page.goto(pathToFileURL(path.join(tmp, 'map/index.html')).href);
    await page.waitForFunction(() => [...document.querySelectorAll('.leaflet-tile')].some(t => t.complete && t.naturalWidth > 0));
    await page.click('#map', {offset: {x: 400, y: 200}});
    assert.match(await page.$eval('#status', e => e.textContent), /Latitude:.*longitude:/);
    await page.select('#mode', 'distance');
    await page.click('#map', {offset: {x: 350, y: 120}});
    await page.click('#map', {offset: {x: 390, y: 150}});
    assert.match(await page.$eval('#status', e => e.textContent), /Approximate distance: [\d.]+ km \(2 points\)/);
    await page.click('#undo');
    assert.match(await page.$eval('#status', e => e.textContent), /at least two/);
    await page.select('#mode', 'area');
    for (const offset of [{x:350,y:120},{x:390,y:120},{x:390,y:160}]) await page.click('#map', {offset});
    const surface = await page.$eval('#status', e => e.textContent);
    assert.match(surface, /Approximate area: [\d.]+ km² \(3 points\)/);
    assert(Number(surface.match(/([\d.]+) km²/)[1]) > 0);
    await page.click('#clear');
    await page.type('#lat', '٣٣٫٣'); await page.type('#lon', '٤٤٫٤'); await page.click('#go');
    assert.match(await page.$eval('#status', e => e.textContent), /Latitude: 33\.3000000, longitude: 44\.4000000/);
    await page.select('#language', 'ar');
    assert.equal(await page.$eval('html', e => e.dir), 'rtl');
    assert.match(await page.$eval('#status', e => e.textContent), /خط العرض/);
    await page.click('#fit');
    assert.equal(await page.$eval('.leaflet-control-attribution', e => e.querySelectorAll('img').length), 0);
    // Only synthetic local JSON in a temporary directory, never a Frappe site.
    const node = (doctype, name) => ({doctype, name});
    const snapshotPath = path.join(tmp, 'fixture.json');
    fs.writeFileSync(snapshotPath, JSON.stringify({version:1, created_at:'fixture', nodes:[node('Person','a'),node('Place','b')],
      edges:[{source:node('Person','a'),target:node('Place','b'),type:'test'}]}));
    await page.click('#records summary');
    const input = await page.$('#record-file'); await input.uploadFile(snapshotPath);
    await page.waitForFunction(() => document.querySelector('#record-state').textContent.includes('2 matching records'));
    await page.click('#record-results button');
    assert.match(await page.$eval('#record-info', e => e.textContent), /Place: b/);
    await page.click('#record-info button');
    assert.match(await page.$eval('#record-info strong', e => e.textContent), /Place: b/);
    await page.type('#record-search', 'Person');
    assert.match(await page.$eval('#record-state', e => e.textContent), /1 matching records/);
    await page.click('#record-close');
    assert.match(await page.$eval('#record-state', e => e.textContent), /closed/);
    // Experimental signed path: fixture key and records never leave this process.
    const signed = await page.evaluate(async () => {
      const keys = await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'}, true, ['sign','verify']);
      const pub = await crypto.subtle.exportKey('jwk', keys.publicKey);
      const iso = ms => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
      const now=Date.now(), source={doctype:'Person',name:'a'}, target={doctype:'Place',name:'b'};
      const body={version:3,site:'site',subject:'account',key_id:'fixture-key',snapshot_id:'0123456789abcdef0123456789abcdef',
        created_at:iso(now-1000),expires_at:iso(now+3600000),payload:{scope:{included_types:['Person','Place'],omitted_types:[],excluded_types:['Event'],relationships:'filtered',consistency:'non_atomic'},
        nodes:[source,target],edges:[{source,target,type:''}]}};
      const raw = new TextEncoder().encode(JSON.stringify(body));
      const domain = new TextEncoder().encode('SIRAJ-OFFLINE-SNAPSHOT-V3\0');
      const message = new Uint8Array(domain.length+raw.length); message.set(domain); message.set(raw,domain.length);
      const signature = new Uint8Array(await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},keys.privateKey,message));
      const b64 = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
      window.SIRAJ_OFFLINE_TRUST={site:'site',subject:'account',key_id:'fixture-key',public_key:{kty:pub.kty,crv:pub.crv,x:pub.x,y:pub.y},
        revoked_snapshot_ids:[],revoked_key_ids:[],revocation_valid_until:iso(now+3600000)};
      return {version:3,body:b64(raw),signature:b64(signature)};
    });
    const signedPath=path.join(tmp, 'signed-fixture.json'); fs.writeFileSync(signedPath, JSON.stringify(signed));
    await page.evaluate(() => { window.fixtureTrust=window.SIRAJ_OFFLINE_TRUST; delete window.SIRAJ_OFFLINE_TRUST; });
    await input.uploadFile(signedPath);
    await page.waitForFunction(() => document.querySelector('#record-state').textContent.includes('rejected'));
    await page.evaluate(() => { window.SIRAJ_OFFLINE_TRUST=window.fixtureTrust; document.querySelector('#record-file').value=''; });
    await input.uploadFile(signedPath);
    await page.waitForFunction(() => document.querySelector('#record-state').textContent.includes('Signature verified'));
    assert.match(await page.$eval('#record-state', e=>e.textContent), /owner: account/);
    await page.click('#record-results button');
    assert.match(await page.$eval('#record-info', e=>e.textContent), /Place: b/);
    await page.click('#record-close');
    await page.evaluate(() => window.SIRAJ_OFFLINE_TRUST.revoked_snapshot_ids.push('0123456789abcdef0123456789abcdef'));
    await input.uploadFile(signedPath);
    await page.waitForFunction(() => document.querySelector('#record-state').textContent.includes('rejected'));
    assert.equal(await page.$$eval('#record-results button', e=>e.length), 0);
    // Synthetic extended v4 stays explicitly unsigned; hierarchy is never inferred.
    const extended=(doctype,name,label,parent=null,details={})=>({doctype,name,label,parent,details});
    const place=extended('Place','r','Region',null,{origin:'<img src=x>'});
    const child=extended('Place','c','District','r');
    const person=extended('Person','p','Researcher',null,{note:'<script>not code</script>'});
    const rich={version:4,created_at:'untrusted',nodes:[place,child,person],
      edges:[{source:node('Person','p'),target:node('Place','c'),type:'visited'}]};
    const richPath=path.join(tmp,'rich-fixture.json'); fs.writeFileSync(richPath,JSON.stringify(rich));
    await input.uploadFile(richPath);
    await page.waitForFunction(() => document.querySelector('#record-state').textContent.includes('3 matching records'));
    assert.match(await page.$eval('#record-state',e=>e.textContent),/UNVERIFIED/);
    await page.click('#record-tree-root');
    assert.match(await page.$eval('#record-tree-state',e=>e.textContent),/Top-level places: 1/);
    await page.evaluate(() => [...document.querySelectorAll('#record-tree-results button')].find(b=>b.textContent==='Show children of Region').click());
    assert.match(await page.$eval('#record-tree-state',e=>e.textContent),/Children of Region: 1/);
    await page.evaluate(() => [...document.querySelectorAll('#record-tree-results button')].find(b=>b.textContent==='District').click());
    assert.match(await page.$eval('#record-info',e=>e.textContent),/Researcher|Person: p/);
    await page.click('#record-info button');
    assert.match(await page.$eval('#record-info',e=>e.textContent),/<script>not code<\/script>/);
    assert.equal(await page.$$eval('#record-info script',x=>x.length),0);
    const cyclePath=path.join(tmp,'cycle-fixture.json'); fs.writeFileSync(cyclePath,JSON.stringify({...rich,nodes:[{...place,parent:'c'},child,person]}));
    await input.uploadFile(cyclePath);
    await page.waitForFunction(() => document.querySelector('#record-state').textContent.includes('rejected'));
    assert.equal(await page.$$eval('#record-tree-results button', x=>x.length),0);
    assert.deepStrictEqual(external, []);
    assert.deepStrictEqual(errors, []);
    console.log('Offline viewer: file:// maps, synthetic extended hierarchy, signed/unsigned status and no external requests passed');
  } finally {
    if (browser) await browser.close();
    fs.rmSync(tmp, {recursive:true, force:true});
  }
})().catch(e => { console.error(e); process.exit(1); });
