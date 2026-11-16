/* Experimental offline P-256 verifier; trust must be provisioned independently. */
(() => {
    'use strict';
    const MAX_BYTES = 2 * 1024 * 1024, MAX_AGE_MS = 7 * 86400000;
    const enc = new TextEncoder(), domain = enc.encode('SIRAJ-OFFLINE-SNAPSHOT-V3\0');
    const shape = (obj, fields) => obj && typeof obj === 'object' && !Array.isArray(obj) &&
        Object.keys(obj).length === fields.length && fields.every(k => Object.hasOwn(obj,k));
    const safe = value => typeof value === 'string' && value.length > 0 && value.length <= 256 && value === value.trim();
    function bytes(value) {
        if (typeof value !== 'string' || !/^[A-Za-z0-9_-]+$/.test(value) || value.length % 4 === 1) throw Error('invalid encoding');
        const raw = atob(value.replace(/-/g,'+').replace(/_/g,'/') + '='.repeat((4 - value.length % 4) % 4));
        return Uint8Array.from(raw, c => c.charCodeAt(0));
    }
    function iso(value) {
        if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(value)) throw Error('invalid time');
        const n = Date.parse(value);
        if (!Number.isFinite(n) || new Date(n).toISOString().replace('.000Z','Z') !== value) throw Error('invalid time');
        return n;
    }
    async function open(envelope, trust, now) {
        if (!globalThis.crypto || !crypto.subtle || !Number.isFinite(now)) throw Error('unavailable crypto');
        if (!shape(envelope, ['version','body','signature']) || envelope.version !== 3 ||
            !shape(trust, ['site','subject','key_id','public_key','revoked_snapshot_ids','revoked_key_ids','revocation_valid_until']) ||
            !safe(trust.site) || !safe(trust.subject) || !safe(trust.key_id) ||
            !Array.isArray(trust.revoked_snapshot_ids) || !Array.isArray(trust.revoked_key_ids) ||
            !trust.revoked_snapshot_ids.every(x => typeof x === 'string' && /^[0-9a-f]{32}$/.test(x)) ||
            !trust.revoked_key_ids.every(safe) || iso(trust.revocation_valid_until) <= now) throw Error('invalid trust policy');
        const jwk = trust.public_key;
        if (!shape(jwk, ['kty','crv','x','y']) || jwk.kty !== 'EC' || jwk.crv !== 'P-256' ||
            !/^[A-Za-z0-9_-]{43}$/.test(jwk.x) || !/^[A-Za-z0-9_-]{43}$/.test(jwk.y)) throw Error('invalid public key');
        const raw = bytes(envelope.body), signature = bytes(envelope.signature);
        if (!raw.length || raw.length > MAX_BYTES || signature.length !== 64) throw Error('invalid size');
        const message = new Uint8Array(domain.length + raw.length); message.set(domain); message.set(raw,domain.length);
        const key = await crypto.subtle.importKey('jwk', jwk, {name:'ECDSA', namedCurve:'P-256'}, false, ['verify']);
        if (!await crypto.subtle.verify({name:'ECDSA', hash:'SHA-256'}, key, signature, message)) throw Error('invalid signature');
        const body = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(raw));
        if (!shape(body, ['version','site','subject','key_id','snapshot_id','created_at','expires_at','payload']) || body.version !== 3 ||
            body.site !== trust.site || body.subject !== trust.subject || body.key_id !== trust.key_id ||
            typeof body.snapshot_id !== 'string' || !/^[0-9a-f]{32}$/.test(body.snapshot_id) ||
            trust.revoked_snapshot_ids.includes(body.snapshot_id) || trust.revoked_key_ids.includes(body.key_id)) throw Error('context or revocation mismatch');
        const issued = iso(body.created_at), expiry = iso(body.expires_at);
        if (issued > now || expiry <= now || expiry <= issued || expiry - issued > MAX_AGE_MS) throw Error('expired or future');
        const p = body.payload;
        if (!shape(p, ['scope','nodes','edges']) || !shape(p.scope, ['included_types','omitted_types','excluded_types','relationships','consistency']) ||
            !Array.isArray(p.scope.included_types) || !Array.isArray(p.scope.omitted_types) || !Array.isArray(p.scope.excluded_types) ||
            !p.scope.included_types.every(safe) || !p.scope.omitted_types.every(safe) || !p.scope.excluded_types.every(safe) ||
            !['filtered','not_authorized'].includes(p.scope.relationships) || p.scope.consistency !== 'non_atomic') throw Error('invalid scope');
        return {data:{version:1, created_at:body.created_at, nodes:p.nodes, edges:p.edges},
                info:{site:body.site, subject:body.subject, created_at:body.created_at, expires_at:body.expires_at,
                      included:p.scope.included_types.join(', '), omitted:p.scope.omitted_types.join(', '),
                      excluded:p.scope.excluded_types.join(', '), relationships:p.scope.relationships}};
    }
    window.sirajSnapshotVerify = {open};
})();
