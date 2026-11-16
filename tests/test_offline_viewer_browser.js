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
    assert.deepStrictEqual(external, []);
    assert.deepStrictEqual(errors, []);
    console.log('Offline viewer: file:// rendering, coordinates, escaped attribution and no external requests passed');
  } finally {
    if (browser) await browser.close();
    fs.rmSync(tmp, {recursive:true, force:true});
  }
})().catch(e => { console.error(e); process.exit(1); });
