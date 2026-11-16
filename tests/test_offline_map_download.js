// npm install --prefix /tmp/siraj-map-test --no-save jsdom@24
// NODE_PATH=/tmp/siraj-map-test/node_modules node tests/test_offline_map_download.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');
const w = new JSDOM('', {runScripts:'outside-only'}).window;
w.eval(fs.readFileSync(path.resolve(__dirname, '../siraj_research/public/js/offline_map_download.js'), 'utf8'));
const plan = w.sirajOfflineDownload.plan;
assert.equal(plan([-180,-85,180,85],0,1).count, 5);
assert.equal(plan([170,-10,-170,10],0,1).count, 5);
assert.equal(plan([0,0,1,1],0,2).count, 3);
for (const v of [[[0,0,0,1],0,1], [[0,-90,1,1],0,1], [[-180,-85,180,85],0,8], [[0,0,1,1],-1,1], [[0,0,1,1],0,23]]) assert.throws(() => plan(...v));
console.log('Offline area planner: bounds, dateline, limits and zoom validation passed');
(async () => {
  const files = [];
  w.JSZip = class { file(name) { files.push(name); } async generateAsync() { return 'zip'; } };
  const pack = {kind:'standard', format:'png', minzoom:0, maxzoom:2, download_allowed:true, attribution:'test'};
  let requests = 0, tileStatus = 200, tileSize = 1, failAsset = false;
  w.fetch = async (url, {signal}) => {
    if (signal.aborted) throw new w.DOMException('Cancelled', 'AbortError');
    if (url.startsWith('/api/')) {
      requests++;
      return {ok:tileStatus===200,status:tileStatus,arrayBuffer:async()=>new ArrayBuffer(tileSize)};
    }
    return {ok:!failAsset,status:failAsset?500:200,arrayBuffer:async()=>new ArrayBuffer(1)};
  };
  const controller = new w.AbortController();
  let progress;
  let result = await w.sirajOfflineDownload.build(pack, [-180,-85,180,85], 0, 0, controller.signal, (...x)=>{progress=x;});
  assert.equal(result.stored,1); assert.equal(result.requested,1); assert.equal(result.bytes,1);
  assert.equal(requests,1); assert.equal(progress[0],1); assert(files.includes('tiles/0/0/0.png')); assert(files.includes('index.html')); assert(files.includes('leaflet/LICENSE'));
  tileStatus=404;
  await assert.rejects(() => w.sirajOfflineDownload.build(pack, [-180,-85,180,85], 0, 0, controller.signal, ()=>{}), /empty/);
  tileStatus=403;
  await assert.rejects(() => w.sirajOfflineDownload.build(pack, [-180,-85,180,85], 0, 0, controller.signal, ()=>{}), /tile/);
  tileStatus=200; tileSize=4*1024*1024+1;
  await assert.rejects(() => w.sirajOfflineDownload.build(pack, [-180,-85,180,85], 0, 0, controller.signal, ()=>{}), /size/);
  tileSize=4*1024*1024;
  await assert.rejects(() => w.sirajOfflineDownload.build(pack, [-180,-85,180,85], 0, 1, controller.signal, ()=>{}), /size/);
  tileSize=1; failAsset=true;
  await assert.rejects(() => w.sirajOfflineDownload.build(pack, [-180,-85,180,85], 0, 0, controller.signal, ()=>{}), /asset/);
  await assert.rejects(() => w.sirajOfflineDownload.build({...pack,download_allowed:false}, [-180,-85,180,85], 0, 0, controller.signal, ()=>{}), /invalid/);
  controller.abort();
  await assert.rejects(() => w.sirajOfflineDownload.build(pack, [-180,-85,180,85], 0, 0, controller.signal, ()=>{}), e=>e.name==='AbortError');
  console.log('Offline download: tile/asset errors, byte limits, licensing opt-in and cancellation passed');
})().catch(e => {console.error(e); process.exitCode=1;});
