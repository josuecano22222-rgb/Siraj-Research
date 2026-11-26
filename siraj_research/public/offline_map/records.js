/* Local, read-only snapshot viewer: no network, persistence, export or sync. */
(() => {
    'use strict';
    const el = id => document.getElementById(id);
    const MAX_BYTES = 2 * 1024 * 1024, MAX_NODES = 2000, MAX_EDGES = 4000, MAX_TEXT = 256, MAX_RESULTS = 100, MAX_LINKS = 100;
    const types = new Set(['Person', 'Institution', 'Place', 'Source']);
    let snapshot = null, nodes = new Map(), links = new Map(), places = new Map(), generation = 0, signedInfo = null, expires = 0, expiryTimer = null;
    const key = node => JSON.stringify([node.doctype, node.name]);
    const text = value => typeof value === 'string' && value.length > 0 && value.length <= MAX_TEXT && value.trim() === value;
    const shape = (obj, fields) => obj && typeof obj === 'object' && !Array.isArray(obj) &&
        Object.keys(obj).length === fields.length && fields.every(f => Object.hasOwn(obj, f));
    function validate(data) {
        if (!shape(data, ['version','created_at','nodes','edges']) || ![1,4].includes(data.version) || !text(data.created_at) ||
            !Array.isArray(data.nodes) || data.nodes.length > MAX_NODES || !Array.isArray(data.edges) || data.edges.length > MAX_EDGES) throw Error('Invalid snapshot');
        const index = new Map(), adjacency = new Map(), tree = new Map([[null, []]]);
        for (const node of data.nodes) {
            const expected = data.version === 1 ? ['doctype','name'] : ['doctype','name','label','details','parent'];
            if (!shape(node, expected) || !types.has(node.doctype) || !text(node.name) || index.has(key(node))) throw Error('Invalid record');
            if (data.version === 4 && (!text(node.label) || !node.details || typeof node.details !== 'object' || Array.isArray(node.details) ||
                Object.keys(node.details).length > 40 || Object.entries(node.details).some(([k,v]) => !text(k) || typeof v !== 'string' || v.length > 1024) ||
                !(node.parent === null || (node.doctype === 'Place' && text(node.parent))))) throw Error('Invalid record details');
            index.set(key(node), node); adjacency.set(key(node), []);
        }
        if (data.version === 4) {
            const parentOf = new Map();
            for (const node of data.nodes) if (node.doctype === 'Place') {
                if (node.parent !== null && !index.has(key({doctype:'Place',name:node.parent}))) throw Error('Missing Place parent');
                parentOf.set(node.name,node.parent);
                if (!tree.has(node.parent)) tree.set(node.parent, []);
                tree.get(node.parent).push(node);
            }
            // Detect self-links and cycles in linear time; never infer a hierarchy from relationships.
            const done = new Set();
            for (const name of parentOf.keys()) {
                let current = name; const path = new Set();
                while (current !== null && !done.has(current)) {
                    if (path.has(current)) throw Error('Place cycle');
                    path.add(current); current = parentOf.get(current);
                }
                for (const item of path) done.add(item);
            }
        }
        for (const edge of data.edges) {
            if (!shape(edge, ['source','target','type']) || !shape(edge.source, ['doctype','name']) || !shape(edge.target, ['doctype','name']) ||
                !types.has(edge.source.doctype) || !types.has(edge.target.doctype) || !text(edge.source.name) || !text(edge.target.name) ||
                !index.has(key(edge.source)) || !index.has(key(edge.target)) || typeof edge.type !== 'string' || edge.type.length > MAX_TEXT) throw Error('Invalid relationship');
            adjacency.get(key(edge.source)).push({edge, outgoing:true});
            if (key(edge.source) !== key(edge.target)) adjacency.get(key(edge.target)).push({edge, outgoing:false});
        }
        return {index, adjacency, tree};
    }
    function button(label, fn) {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.addEventListener('click', fn); return b;
    }
    function stillValid() {
        if (signedInfo && Date.now() >= expires) { generation++; reset('Signed snapshot expired or revocation policy is stale; no records loaded.'); return false; }
        return true;
    }
    function open(node, offset = 0) {
        if (!snapshot || !stillValid()) return;
        const info = el('record-info'); info.replaceChildren();
        const title = document.createElement('strong'); title.textContent = node.doctype + ': ' + (node.label || node.name); info.append(title);
        if (snapshot.version === 4) {
            const id = document.createElement('p'); id.textContent = 'Identifier: ' + node.name; info.append(id);
            const details = document.createElement('ul');
            for (const [field, value] of Object.entries(node.details)) {
                const li = document.createElement('li'); li.textContent = field + ': ' + value; details.append(li);
            }
            if (details.children.length) info.append(details);
        }
        const related = links.get(key(node)) || [], list = document.createElement('ul');
        offset = Math.max(0, Math.min(offset, Math.max(0, Math.ceil(related.length / MAX_LINKS) - 1) * MAX_LINKS));
        for (const {edge, outgoing} of related.slice(offset, offset + MAX_LINKS)) {
            const other = nodes.get(key(outgoing ? edge.target : edge.source));
            const li = document.createElement('li');
            const prefix = document.createElement('span'); prefix.textContent = (outgoing ? '→ ' : '← ') + (edge.type || 'Relationship') + ': ';
            li.append(prefix, button(other.doctype + ': ' + other.name, () => open(other))); list.append(li);
        }
        const summary = document.createElement('p');
        summary.textContent = related.length ? related.length + (related.length === 1 ? ' relationship' : ' relationships') + ' in this snapshot; showing ' + (offset + 1) + '–' + Math.min(offset + MAX_LINKS, related.length) + '.' : 'No relationships in this snapshot.';
        info.append(summary);
        if (related.length) info.append(list);
        if (offset > 0) info.append(button('Previous relationships', () => open(node, offset - MAX_LINKS)));
        if (offset + MAX_LINKS < related.length) info.append(button('Next relationships', () => open(node, offset + MAX_LINKS)));
    }
    function render() {
        const results = el('record-results'); results.replaceChildren();
        if (!snapshot || !stillValid()) return;
        const query = el('record-search').value.toLocaleLowerCase(), type = el('record-type').value;
        const matching = snapshot.nodes.filter(n => (!type || n.doctype === type) && (n.doctype + ' ' + n.name + ' ' + (n.label || '')).toLocaleLowerCase().includes(query));
        for (const node of matching.slice(0, MAX_RESULTS)) {
            const li = document.createElement('li'); li.append(button(node.doctype + ': ' + node.name, () => open(node))); results.append(li);
        }
        const status = signedInfo ? 'Signature verified against configured key; site: ' + signedInfo.site + ', owner: ' + signedInfo.subject +
            ', created: ' + signedInfo.created_at + ', age at last refresh: ' + Math.max(0, Math.floor((Date.now() - Date.parse(signedInfo.created_at)) / 60000)) + ' min, expires: ' + signedInfo.expires_at + ', included: ' + signedInfo.included +
            ', omitted: ' + signedInfo.omitted + ', excluded: ' + signedInfo.excluded + ', relationships: ' + signedInfo.relationships +
            '. Permission and identity are not rechecked; contents are unencrypted and scan was non-atomic. ' :
            'UNVERIFIED disconnected read-only snapshot. File date is untrusted. ';
        el('record-state').textContent = status + matching.length + ' matching records; showing at most ' + MAX_RESULTS + '.';
    }
    function reset(message) {
        snapshot = null; nodes = new Map(); links = new Map(); places = new Map(); signedInfo = null; expires = 0;
        if (expiryTimer) { clearTimeout(expiryTimer); expiryTimer = null; }
        el('record-results').replaceChildren(); el('record-info').replaceChildren();
        el('record-tree-results').replaceChildren(); el('record-tree-state').textContent = 'Load a snapshot with an explicit Place hierarchy.';
        el('record-type').replaceChildren(new Option('All types', ''));
        el('record-state').textContent = message;
    }
    function showPlaces(parent = null, offset = 0) {
        if (!snapshot || !stillValid() || snapshot.version !== 4) return;
        const list = el('record-tree-results'); list.replaceChildren();
        const children = places.get(parent) || [];
        offset = Math.max(0, Math.min(offset, Math.max(0, Math.ceil(children.length / MAX_RESULTS) - 1) * MAX_RESULTS));
        const parentNode = parent === null ? null : nodes.get(key({doctype:'Place',name:parent}));
        el('record-tree-state').textContent = (parentNode ? 'Children of ' + parentNode.label : 'Top-level places') + ': ' + children.length + '.';
        if (parentNode) list.append(button('Up one level', () => showPlaces(parentNode.parent)));
        for (const child of children.slice(offset,offset + MAX_RESULTS)) {
            const li = document.createElement('li');
            li.append(button(child.label, () => open(child)));
            if ((places.get(child.name) || []).length) li.append(button('Show children of ' + child.label, () => showPlaces(child.name)));
            list.append(li);
        }
        if (offset > 0) list.append(button('Previous places', () => showPlaces(parent, offset - MAX_RESULTS)));
        if (offset + MAX_RESULTS < children.length) list.append(button('Next places', () => showPlaces(parent, offset + MAX_RESULTS)));
    }
    el('record-tree-root').addEventListener('click', () => {
        if (!snapshot || snapshot.version !== 4) {
            el('record-tree-state').textContent = 'Place hierarchy is not included in this snapshot.'; return;
        }
        showPlaces();
    });
    el('record-file').addEventListener('change', async event => {
        const token = ++generation, file = event.target.files[0];
        reset('Loading local snapshot…');
        try {
            if (!file || file.size > MAX_BYTES) throw Error('Invalid file');
            const envelope = JSON.parse(await file.text());
            let data = envelope, info = null, deadline = 0;
            if (envelope && envelope.version === 3) {
                if (!window.sirajSnapshotVerify || !window.SIRAJ_OFFLINE_TRUST) throw Error('No independently configured trust');
                const verified = await window.sirajSnapshotVerify.open(envelope, window.SIRAJ_OFFLINE_TRUST, Date.now());
                data = verified.data; info = verified.info;
                deadline = Math.min(Date.parse(info.expires_at), Date.parse(window.SIRAJ_OFFLINE_TRUST.revocation_valid_until));
                if (!Number.isFinite(deadline) || deadline <= Date.now()) throw Error('Expired');
            }
            const checked = validate(data);
            if (token !== generation) return;
            snapshot = data; nodes = checked.index; links = checked.adjacency; places = checked.tree; signedInfo = info; expires = deadline;
            if (info) expiryTimer = setTimeout(() => { if (token === generation) stillValid(); }, Math.max(0, deadline - Date.now()));
            for (const type of [...new Set(data.nodes.map(node => node.doctype))].sort()) el('record-type').append(new Option(type, type));
            render();
        } catch (_) {
            if (token === generation) reset('Snapshot rejected. Check format, limits and relationship targets; no records loaded.');
        }
    });
    el('record-close').addEventListener('click', () => {
        generation++; el('record-file').value = ''; el('record-search').value = '';
        reset('Snapshot closed. This viewer does not connect to a server.');
    });
    el('record-search').addEventListener('input', render);
    el('record-type').addEventListener('change', render);
})();
