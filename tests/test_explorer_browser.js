// Real-browser visual/interaction smoke with synthetic data, not a Frappe integration test.
// npm install --prefix /tmp/siraj-browser --no-save puppeteer-core@24.2.0 @sparticuz/chromium@133.0.0 jquery@3.7.1
// NODE_PATH=/tmp/siraj-browser/node_modules node tests/test_explorer_browser.js
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');
const {execFileSync} = require('child_process');
const {pathToFileURL} = require('url');
const puppeteer = require('puppeteer-core');
const ROOT = path.resolve(__dirname, '..');
const asset = name => path.join(ROOT, 'siraj_research/public', name);

async function executable() {
	if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
	const chromium = require('@sparticuz/chromium');
	const bin = await chromium.executablePath();
	// The Lambda bundle includes NSS on systems where Chromium's NSS is absent.
	const dir = path.dirname(require.resolve('@sparticuz/chromium/package.json'));
	const lambdaFs = require(path.join(dir, 'build/lambdafs.js')).default;
	const libs = await lambdaFs.inflate(path.join(dir, 'bin/al2023.tar.br'));
	process.env.LD_LIBRARY_PATH = path.join(libs, 'lib') + ':' + (process.env.LD_LIBRARY_PATH || '');
	return bin;
}

(async () => {
	const browser = await puppeteer.launch({executablePath: await executable(), args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'], headless: true});
	const page = await browser.newPage();
	const errors = [], tileRequests = [];
	await page.setRequestInterception(true);
	page.on('request', request => {
		if (request.url().startsWith('https://site.test/api/method/siraj_research.local_maps.tile?')) {
			tileRequests.push(request.url());
			request.respond({status:200, contentType:'image/png', body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/a3sAAAAASUVORK5CYII=', 'base64')});
		} else request.continue();
	});
	page.on('pageerror', error => errors.push(error.stack));
	page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
	try {
		await page.setViewport({width: 1440, height: 1000});
		await page.setContent('<!doctype html><html><head><base href="https://site.test/"></head><body><div id="host"></div></body></html>');
		for (const file of ['vendor/leaflet/leaflet.css', 'css/siraj_explorer.css']) await page.addStyleTag({path: asset(file)});
		for (const file of [require.resolve('jquery/dist/jquery.js'), ...['vendor/leaflet/leaflet.js', 'vendor/leaflet-markercluster/leaflet.markercluster.js', 'vendor/topojson/topojson-client.min.js', 'vendor/vis-network/vis-network.min.js', 'vendor/d3/d3.min.js', 'vendor/d3-sankey/d3-sankey.min.js', 'js/structure_deck.js', 'vendor/jszip/jszip.min.js', 'js/offline_map_download.js'].map(asset)]) await page.addScriptTag({path: file});
		const world = JSON.parse(fs.readFileSync(asset('vendor/world-atlas/countries-110m.json'), 'utf8'));
		const exportAssets = Object.fromEntries(['offline_map/index.html', 'offline_map/viewer.js', 'vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css', 'vendor/leaflet/LICENSE', ...['layers.png','layers-2x.png','marker-icon.png','marker-icon-2x.png','marker-shadow.png'].map(x => 'vendor/leaflet/images/' + x)].map(name => [name, fs.readFileSync(asset(name)).toString('base64')]));
		await page.evaluate((world, exportAssets) => {
			window.__ = (s, args) => args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s;
			window.fetch = async url => {
				if (url.includes('countries-110m')) return {ok:true, json:async()=>world};
				const key = url.replace('/assets/siraj_research/', '');
				const encoded = url.startsWith('/api/method/siraj_research.local_maps.tile?') ? 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/a3sAAAAASUVORK5CYII=' : exportAssets[key];
				return encoded ? {ok:true,status:200,arrayBuffer:async()=>Uint8Array.from(atob(encoded), c=>c.charCodeAt(0)).buffer} : {ok:false,status:404};
			};
			window.downloads = [];
			URL.createObjectURL = blob => { window.downloads.push(blob); return 'blob:test'; };
			URL.revokeObjectURL = () => {};
			HTMLAnchorElement.prototype.click = function () {};
			const countries = ['Iraq', 'Jordan', 'Syria', 'Lebanon', 'Yemen', 'Egypt', 'Turkey'];
			const groups = countries.map(label => ({label, count: 60, group_count: 5, children: ['Researcher', 'Historian', 'Analyst', 'Officer', 'Author'].map(label => ({label, count: 12, group_count: 3, children: [3, 4, 5].map((count, i) => ({label: ['Draft', 'Reviewed', 'Published'][i], count, group_count: 0, children: []}))}))}));
			const nodes = Array.from({length: 20}, (_, i) => ({doctype: i % 2 ? 'Person' : 'Institution', name: 'n' + i, label: 'Record ' + i, details: {Status: 'Draft'}}));
			nodes[1].label = 'Record <1> & friends';
			const graph = {nodes, edges: nodes.slice(1).map((n, i) => ({name: 'r' + i, source: [nodes[0].doctype, nodes[0].name], target: [n.doctype, n.name], type: 'Member', direction: 'Directed'})), truncated: []};
			graph.edges.push({name:'parallel', source:[nodes[0].doctype,nodes[0].name], target:[nodes[1].doctype,nodes[1].name], type:'Parallel', direction:'Symmetric'}, {name:'loop', source:[nodes[1].doctype,nodes[1].name], target:[nodes[1].doctype,nodes[1].name], type:'Loop', direction:'Directed'});
			const points = nodes.map((n, i) => ({...n, latitude: 30 + i * .25, longitude: 43 + i * .35}));
			window.frappe = {pages: {'siraj-explorer': {}}, ui: {make_app_page: ({parent}) => ({main: $(parent)})}, require: async () => {}, set_route() {}, call: async ({method}) => ({message: method.endsWith('available_packs') ? [{kind:'aerial', format:'png', download_allowed:true, minzoom:0, maxzoom:2, attribution:'<img src=x onerror=alert(1)>'}] : method.endsWith('geographic_data') ? {points, truncated: []} : method.endsWith('relationship_data') ? graph : {doctype: 'Person', dimensions: ['Nationality', 'Classification', 'Status'], count: 420, group_count: 7, children: groups}})};
		}, world, exportAssets);
		await page.addScriptTag({path: path.join(ROOT, 'siraj_research/siraj_research/page/siraj_explorer/siraj_explorer.js')});
		await page.evaluate(() => frappe.pages['siraj-explorer'].on_page_load(document.getElementById('host')));
		await page.waitForSelector('.sx-record-item');
		assert.strictEqual(await page.$$eval('.sx-record-item', list => list.length), 20);
		await page.waitForFunction(() => !!document.querySelector('select[aria-label=Basemap] option[value=pack-aerial]'));
		await page.select('select[aria-label=Basemap]', 'pack-aerial');
		await page.waitForFunction(() => [...document.querySelectorAll('.leaflet-tile')].some(t => t.complete && t.naturalWidth > 0));
		assert(tileRequests.length > 0);
		assert.equal(await page.$eval('.leaflet-control-attribution', e => e.querySelectorAll('img').length), 0);
		await page.evaluate(() => { const panel = document.querySelector('.sx-area-fields').parentElement; panel.open = true; });
		await page.evaluate(() => [...document.querySelectorAll('.sx-area-fields button')].find(b=>b.textContent==='Use current map area').click());
		await page.evaluate(() => [...document.querySelectorAll('.sx-area-fields button')].find(b=>b.textContent==='Download ZIP').click());
		await page.waitForFunction(() => window.downloads.length > 0);
		const zipFiles = await page.evaluate(async () => Object.keys((await JSZip.loadAsync(await window.downloads[0].arrayBuffer())).files));
		assert(zipFiles.includes('index.html') && zipFiles.includes('viewer.js') && zipFiles.some(n=>/^tiles\/\d+\/\d+\/\d+\.png$/.test(n)));
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'siraj-ui-download-'));
		try {
			const encoded = await page.evaluate(async () => {
				const bytes = new Uint8Array(await window.downloads[0].arrayBuffer()); let binary = '';
				for (const byte of bytes) binary += String.fromCharCode(byte);
				return btoa(binary);
			});
			fs.writeFileSync(path.join(dir, 'map.zip'), Buffer.from(encoded, 'base64'));
			execFileSync('python3', ['-c', 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])', path.join(dir, 'map.zip'), path.join(dir, 'map')]);
			const offline = await browser.newPage(), external = [], offlineErrors = [];
			offline.on('request', req => { if (!req.url().startsWith('file:')) external.push(req.url()); });
			offline.on('pageerror', err => offlineErrors.push(String(err)));
			await offline.goto(pathToFileURL(path.join(dir, 'map', 'index.html')).href);
			await offline.waitForFunction(() => [...document.querySelectorAll('.leaflet-tile')].some(t => t.complete && t.naturalWidth > 0));
			assert.deepStrictEqual(external, []); assert.deepStrictEqual(offlineErrors, []);
			await offline.close();
		} finally { fs.rmSync(dir, {recursive:true, force:true}); }


		await page.select('select[aria-label=Basemap]', 'local');
		await page.click('.sx-record-item');
		assert.strictEqual(await page.$eval('.sx-aside h4', e => e.textContent), 'Record 0');
		await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.textContent === 'Structures').click());
		await page.waitForSelector('.sd-tabs');
		for (const mode of ['treemap', 'rings', 'flow', 'matrix', 'discs', 'tree']) {
			await page.click(`.sd-tabs [data-mode="${mode}"]`);
			assert(await page.$('.sd-stage svg'), `${mode} must render an SVG`);
			assert((await page.$$('.sd-mark')).length, `${mode} must render selectable marks`);
			assert.strictEqual(await page.$$eval('.sd-stage [d]', els => els.filter(e => /NaN|Infinity/.test(e.getAttribute('d'))).length), 0);
		}
		await page.select('select[aria-label="Structure depth"]', '1');
		assert(await page.$eval('.sd-stage', el => el.textContent.includes('▸ 5')), 'depth-collapsed tree must show the group count');
		await page.select('select[aria-label="Structure depth"]', '3');
		await page.focus('.sd-stage'); await page.keyboard.press('2');
		assert(await page.$eval('.sd-tabs [data-mode="rings"]', el => el.classList.contains('active')), 'number key should switch layout');
		await page.click('.sd-tabs [data-mode="tree"]');
		await page.click('.sd-toggle[aria-label="Expand branch"]');
		assert((await page.$$('.sd-mark')).length > 8, 'tree expansion must reveal children');
		await page.type('.sd-find', 'Historian'); await page.keyboard.press('Enter');
		assert.strictEqual(await page.$eval('.sx-aside h4', el => el.textContent), 'Historian');
		assert(await page.$eval('.sd-crumbs', el => el.textContent.includes('Iraq')));
		await page.click('.sd-tabs [data-mode="flow"]');
		const stroke = await page.$eval('.sd-stage path.sd-mark', el => ({stroke: getComputedStyle(el).stroke, width: parseFloat(getComputedStyle(el).strokeWidth)}));
		assert(stroke.width > 1 && stroke.stroke !== 'rgb(255, 255, 255)', 'flow links must be visible');
		await page.evaluate(() => [...document.querySelectorAll('.sd-bar button')].find(b => b.textContent === 'Zoom in').click());
		assert(await page.$eval('.sd-stage svg > g', el => /scale\(1.25\)/.test(el.getAttribute('transform'))));
		await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.textContent === 'Relationship map').click());
		await page.waitForSelector('select[aria-label="Relationship layout"]');
		await page.evaluate(() => [...document.querySelectorAll('.sx-tools button')].find(b => b.textContent === 'Export SVG').click());
		const networkExport = await page.evaluate(() => window.downloads.at(-1).text());
		assert(networkExport.includes('Record 0') && networkExport.includes('marker-end') && networkExport.includes('Member') && networkExport.includes('Loop') && networkExport.includes('Parallel'));
		assert(!networkExport.includes('NaN') && !networkExport.includes('Infinity'));
		assert(networkExport.includes('Record &lt;1&gt; &amp; friends'));
		assert(await page.evaluate(text => !new DOMParser().parseFromString(text, 'image/svg+xml').querySelector('parsererror'), networkExport), 'network SVG must parse');
		await page.select('select[aria-label="Relationship layout"]', 'matrix');
		assert.strictEqual(await page.$$eval('.sx-matrix-cell', list => list.length), 21);
		await page.evaluate(() => [...document.querySelectorAll('.sx-tools button')].find(b => b.textContent === 'Export SVG').click());
		const matrixExport = await page.evaluate(() => window.downloads.at(-1).text());
		assert(matrixExport.includes('Record 0') && matrixExport.includes('font-family="sans-serif"') && matrixExport.includes('stroke-width="1"'));
		assert(await page.evaluate(text => !new DOMParser().parseFromString(text, 'image/svg+xml').querySelector('parsererror'), matrixExport), 'matrix SVG must parse');
		await page.click('.sx-matrix-cell');
		assert.strictEqual(await page.$eval('.sx-aside h4', e => e.textContent), 'Parallel');
		await page.type('.sx-atlas-rail input[type="search"]', 'Record 0');
		await page.evaluate(() => [...document.querySelectorAll('.sx-tools button')].find(b => b.textContent === 'Export SVG').click());
		const filteredExport = await page.evaluate(() => window.downloads.at(-1).text());
		assert(filteredExport.includes('Record 0') && !filteredExport.includes('Record 2'));
		await page.setViewport({width: 390, height: 844});
		await page.evaluate(() => { document.documentElement.dir = 'rtl'; [...document.querySelectorAll('button')].find(b => b.textContent === 'Structures').click(); });
		await page.waitForSelector('.sd-tabs');
		await page.click('.sd-tabs [data-mode="rings"]');
		assert.strictEqual(await page.$eval('.sd-stage svg', svg => svg.getAttribute('direction')), 'ltr');
		assert(await page.$eval('.sd-stage', el => el.getBoundingClientRect().width > 0));
		assert.deepStrictEqual(errors, []);
		console.log('Headless Chromium smoke passed: local map, six structure layouts, tree expansion, flow visibility, zoom and relationship matrix.');
	} finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
