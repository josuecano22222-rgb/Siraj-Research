// Synthetic browser API stub test; not an application load test.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const {performance} = require('perf_hooks');
const code = fs.readFileSync('docs/qa/load-probe.js', 'utf8');
let active = 0, peak = 0, paths = [];
const context = {window:{}, performance, setTimeout, clearTimeout, AbortController, Object, Array, Math, Number,
  fetch: async (url, options) => {
    paths.push(url); assert.equal(options.credentials, 'same-origin');
    active++; peak = Math.max(peak, active);
    let count=0;
    return {status:200, body:{getReader:()=>({read:async()=>{await new Promise(r=>setTimeout(r,1));if (count++) {active--;return {done:true};}return {done:false,value:new Uint8Array(3)};},cancel:async()=>{active--;}})}};
  }};
vm.runInNewContext(code, context);
(async()=>{
  const probe=context.window.sirajLoadProbe;
  await assert.rejects(()=>probe('https://bad',1,1),/limits/);
  await assert.rejects(()=>probe('geography',6,6),/limits/);
  await assert.rejects(()=>probe('geography',1,21),/limits/);
  const result=await probe('geography',2,4);
  assert.equal(result.successful,4); assert.equal(result.attempted_requests,4);
  assert.equal(result.total_response_bytes,12); assert.equal(peak,2);
  assert(paths.every(p=>p==='/api/method/siraj_research.visualization.geographic_data'));
  assert.equal(result.statuses['200'],4); assert(result.p95_ms >= result.p50_ms);
  assert(!JSON.stringify(result).includes('private record'));
  console.log('Load probe bounds, same-origin paths and aggregate metrics passed (synthetic only).');
})().catch(e=>{console.error(e);process.exitCode=1;});
