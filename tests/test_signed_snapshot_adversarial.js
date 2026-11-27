// Synthetic ephemeral keys and data only; no site, trust provisioning or real export.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const {webcrypto} = require('crypto');
const {TextEncoder,TextDecoder} = require('util');
const context = {window:{},crypto:webcrypto,TextEncoder,TextDecoder,Uint8Array,atob,Date,JSON,Object,Array,Number,Error,Set};
vm.runInNewContext(fs.readFileSync('siraj_research/public/offline_map/snapshot_verify.js','utf8'),context);
const open = context.window.sirajSnapshotVerify.open;
const b64 = data => Buffer.from(data).toString('base64url');
const now = Date.parse('2026-01-01T12:00:00Z');
const body = () => ({version:3,site:'site',subject:'reader',key_id:'old',snapshot_id:'0123456789abcdef0123456789abcdef',
 created_at:'2026-01-01T00:00:00Z',expires_at:'2026-01-02T00:00:00Z',payload:{
 scope:{included_types:['Person'],omitted_types:[],excluded_types:['Event'],relationships:'filtered',consistency:'non_atomic'},
 nodes:[{doctype:'Person',name:'fixture'}],edges:[]}});
async function key() {
 const pair = await webcrypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},true,['sign','verify']);
 const {kty,crv,x,y} = await webcrypto.subtle.exportKey('jwk',pair.publicKey);
 return {pair,public_key:{kty,crv,x,y}};
}
async function sign(raw, pair) {
 const data = Buffer.isBuffer(raw) ? raw : Buffer.from(raw);
 const signature = await webcrypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},pair.privateKey,
   Buffer.concat([Buffer.from('SIRAJ-OFFLINE-SNAPSHOT-V3\0'),data]));
 return {version:3,body:b64(data),signature:b64(signature)};
}
(async()=>{
 const old = await key(), next = await key();
 const trust = {site:'site',subject:'reader',key_id:'old',public_key:old.public_key,
                revoked_snapshot_ids:[],revoked_key_ids:[],revocation_valid_until:'2026-01-03T00:00:00Z'};
 const original = await sign(JSON.stringify(body()),old.pair);
 const rotatedBody = body(); rotatedBody.key_id='new';
 const rotated = await sign(JSON.stringify(rotatedBody),next.pair);
 const newTrust = {...trust,key_id:'new',public_key:next.public_key,revoked_key_ids:['old']};
 // A prototype policy has exactly one key, not a key-ring or a rotation protocol.
 await open(original,trust,now); await open(rotated,newTrust,now);
 await assert.rejects(()=>open(rotated,trust,now)); await assert.rejects(()=>open(original,newTrust,now));
 await assert.rejects(()=>open(original,{...trust,key_id:'unknown'},now));
 await assert.rejects(()=>open(original,{...trust,public_key:next.public_key},now));
 await assert.rejects(()=>open(original,{...trust,revoked_key_ids:['old']},now));
 await assert.rejects(()=>open(original,{...trust,revocation_valid_until:'2026-01-01T12:00:00Z'},now));
 await open(original,trust,Date.parse('2026-01-01T00:00:00Z'));
 await open(original,trust,Date.parse('2026-01-01T23:59:59.999Z'));
 await assert.rejects(()=>open(original,trust,Date.parse('2025-12-31T23:59:59.999Z')));
 await assert.rejects(()=>open(original,trust,Date.parse('2026-01-02T00:00:00Z')));
 await assert.rejects(()=>open(original,{...trust,site:'elsewhere'},now));
 await assert.rejects(()=>open(original,{...trust,subject:'else'},now));
 const modified = body(); modified.subject='else';
 await assert.rejects(()=>open({...original,body:b64(JSON.stringify(modified))},trust,now));
 // Replay is currently accepted until expiry or supplied revocation: document it, don't claim prevention.
 await open(original,trust,now); await open(original,trust,now);
 await assert.rejects(()=>open(original,{...trust,revoked_snapshot_ids:[body().snapshot_id]},now));
 const badPayloads = [null, {}, {...body().payload,nodes:'wrong'},
  {...body().payload,nodes:[{doctype:'Person',name:'fixture'},{doctype:'Person',name:'fixture'}]},
  {...body().payload,nodes:[{doctype:'Siraj Event',name:'fixture'}],scope:{...body().payload.scope,included_types:['Siraj Event']}},
  {...body().payload,scope:{...body().payload.scope,included_types:[]}},
  {...body().payload,scope:{...body().payload.scope,omitted_types:['Person']}},
  {...body().payload,edges:[{source:{doctype:'Person',name:'fixture'},target:{doctype:'Person',name:'missing'},type:''}]},
  {...body().payload,scope:{...body().payload.scope,relationships:'not_authorized'},edges:[{source:{doctype:'Person',name:'fixture'},target:{doctype:'Person',name:'fixture'},type:''}]}];
 for (const payload of badPayloads) {
   const malformed = body(); malformed.payload=payload;
   await assert.rejects(()=>sign(JSON.stringify(malformed),old.pair).then(env=>open(env,trust,now)));
 }
 // Valid signatures on ambiguous JSON/invalid UTF-8 must still be rejected.
 const raw = JSON.stringify(body());
 const badRaw = [raw.replace('"site":"site"','"site":"site","site":"site"'),
   raw.replace('"site":"site"','"site":"site","s\\u0069te":"site"'),
   Buffer.from([0xff,0xfe])];
 for (const data of badRaw) await assert.rejects(()=>sign(data,old.pair).then(env=>open(env,trust,now)));
 const deep = body(); let nested = []; for (let i=0;i<70;i++) nested=[nested]; deep.payload.nodes=nested;
 await assert.rejects(()=>sign(JSON.stringify(deep),old.pair).then(env=>open(env,trust,now)), /nesting limit/);
 console.log('Signed snapshot adversarial cases passed: rotation, unknown/revoked keys, stale policy, time boundaries, context, replay limitation and malformed signed bodies (synthetic Node WebCrypto only).');
})().catch(error=>{console.error(error);process.exitCode=1;});
