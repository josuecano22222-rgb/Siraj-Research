// Synthetic cryptography test with built-in Node WebCrypto, no Frappe or real data.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const {webcrypto} = require('crypto');
const {TextEncoder, TextDecoder} = require('util');
const context = {window:{}, crypto:webcrypto, TextEncoder, TextDecoder, Uint8Array, atob, Date, JSON, Object, Array, Number, Error};
vm.runInNewContext(fs.readFileSync('siraj_research/public/offline_map/snapshot_verify.js','utf8'), context);
const open = context.window.sirajSnapshotVerify.open;
const b64 = bytes => Buffer.from(bytes).toString('base64url');
async function generatedFixture() {
  const keys = await webcrypto.subtle.generateKey({name:'ECDSA', namedCurve:'P-256'}, true, ['sign','verify']);
  const pub = await webcrypto.subtle.exportKey('jwk', keys.publicKey);
  const body = {version:3, site:'site', subject:'account', key_id:'key', snapshot_id:'0123456789abcdef0123456789abcdef',
    created_at:'2026-01-01T00:00:00Z', expires_at:'2026-01-02T00:00:00Z', payload:{
      scope:{included_types:['Person'],omitted_types:[],excluded_types:['Event','Research Event'],relationships:'filtered',consistency:'non_atomic'},
      nodes:[{doctype:'Person',name:'example'}],edges:[]}};
  const raw = Buffer.from(JSON.stringify(body));
  const signature = await webcrypto.subtle.sign({name:'ECDSA',hash:'SHA-256'}, keys.privateKey,
    Buffer.concat([Buffer.from('SIRAJ-OFFLINE-SNAPSHOT-V3\0'),raw]));
  return {envelope:{version:3,body:b64(raw),signature:b64(signature)}, trust:{site:'site',subject:'account',key_id:'key',
    public_key:{kty:pub.kty,crv:pub.crv,x:pub.x,y:pub.y}, revoked_snapshot_ids:[],revoked_key_ids:[],revocation_valid_until:'2026-01-03T00:00:00Z'}};
}
(async()=>{
  const {envelope, trust} = process.argv.includes('--python-fixture') ? JSON.parse(fs.readFileSync(0,'utf8')) : await generatedFixture();
  const now=Date.parse('2026-01-01T01:00:00Z');
  const result=await open(envelope,trust,now);
  assert.equal(result.info.subject,'account'); assert.equal(result.data.nodes[0].name,'example');
  await assert.rejects(()=>open({...envelope,body:envelope.body.slice(0,-2)+'AA'},trust,now));
  await assert.rejects(()=>open({...envelope,signature:'A'.repeat(86)},trust,now));
  await assert.rejects(()=>open(envelope,{...trust,subject:'other'},now));
  await assert.rejects(()=>open(envelope,{...trust,site:'other'},now));
  const otherKeys = await webcrypto.subtle.generateKey({name:'ECDSA', namedCurve:'P-256'}, true, ['sign','verify']);
  const otherPub = await webcrypto.subtle.exportKey('jwk', otherKeys.publicKey);
  await assert.rejects(()=>open(envelope,{...trust,public_key:{kty:otherPub.kty,crv:otherPub.crv,x:otherPub.x,y:otherPub.y}},now));
  await assert.rejects(()=>open(envelope,{...trust,key_id:'other'},now));
  await assert.rejects(()=>open(envelope,{...trust,revoked_key_ids:['key']},now));
  const actual=JSON.parse(Buffer.from(envelope.body,'base64url').toString('utf8')).snapshot_id;
  await assert.rejects(()=>open(envelope,{...trust,revoked_snapshot_ids:[actual]},now));
  await assert.rejects(()=>open(envelope,{...trust,revocation_valid_until:'2026-01-01T00:00:00Z'},now));
  await assert.rejects(()=>open(envelope,trust,Date.parse('2026-01-02T00:00:00Z')));
  await assert.rejects(()=>open(envelope,trust,Date.parse('2025-12-31T23:59:59Z')));
  await assert.rejects(()=>open(envelope,undefined,now));
  await assert.rejects(()=>open({...envelope,version:2},trust,now));
  console.log('Signed snapshot crypto: signature, context, expiration and supplied revocations passed (synthetic only).');
})().catch(e=>{console.error(e);process.exitCode=1;});
