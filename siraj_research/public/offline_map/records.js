/* Local, read-only snapshot viewer: no network, persistence, export or sync. */
(() => {
    'use strict';
    const el = id => document.getElementById(id);
    const MAX_BYTES = 2 * 1024 * 1024, MAX_NODES = 2000, MAX_EDGES = 4000, MAX_TEXT = 256, MAX_RESULTS = 100;
    const types = new Set(['Person', 'Institution', 'Place', 'Source', 'SIRAJ Research Event']);
    let snapshot = null, nodes = new Map(), generation = 0;
    const key = node => JSON.stringify([node.doctype, node.name]);
    const text = value => typeof value === 'string' && value.length > 0 && value.length <= MAX_TEXT && value.trim() === value;
    const shape = (obj, fields) => obj && typeof obj === 'object' && !Array.isArray(obj) &&
        Object.keys(obj).length === fields.length && fields.every(f => Object.hasOwn(obj, f));
    function validate(data) {
        if (!shape(data, ['version','created_at','nodes','edges']) || data.version !== 1 || !text(data.created_at) ||
            !Array.isArray(data.nodes) || data.nodes.length > MAX_NODES || !Array.isArray(data.edges) || data.edges.length > MAX_EDGES) throw Error('Invalid snapshot');
        const index = new Map();
        for (const node of data.nodes) {
            if (!shape(node, ['doctype','name']) || !types.has(node.doctype) || !text(node.name) || index.has(key(node))) throw Error('Invalid record');
            index.set(key(node), node);
        }
        for (const edge of data.edges) {
            if (!shape(edge, ['source','target','type']) || !shape(edge.source, ['doctype','name']) || !shape(edge.target, ['doctype','name']) ||
                !types.has(edge.source.doctype) || !types.has(edge.target.doctype) || !text(edge.source.name) || !text(edge.target.name) ||
                !index.has(key(edge.source)) || !index.has(key(edge.target)) || typeof edge.type !== 'string' || edge.type.length > MAX_TEXT) throw Error('Invalid relationship');
        }
        return index;
    }
    function button(label, fn) {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.addEventListener('click', fn); return b;
    }
    function open(node) {
        const info = el('record-info'); info.replaceChildren();
        const title = document.createElement('strong'); title.textContent = node.doctype + ': ' + node.name; info.append(title);
        const list = document.createElement('ul'); let count = 0;
        for (const edge of snapshot.edges) {
            const isSource = key(edge.source) === key(node), isTarget = key(edge.target) === key(node);
            if (!isSource && !isTarget) continue;
            const other = nodes.get(key(isSource ? edge.target : edge.source));
            const li = document.createElement('li');
            const prefix = document.createElement('span'); prefix.textContent = (isSource ? '→ ' : '← ') + (edge.type || 'Relationship') + ': ';
            li.append(prefix, button(other.doctype + ': ' + other.name, () => open(other))); list.append(li); count++;
        }
        if (!count) { const p = document.createElement('p'); p.textContent = 'No relationships in this snapshot.'; info.append(p); }
        else info.append(list);
    }
    function render() {
        const results = el('record-results'); results.replaceChildren();
        if (!snapshot) return;
        const query = el('record-search').value.toLocaleLowerCase(), type = el('record-type').value;
        const matching = snapshot.nodes.filter(n => (!type || n.doctype === type) && (n.doctype + ' ' + n.name).toLocaleLowerCase().includes(query));
        for (const node of matching.slice(0, MAX_RESULTS)) {
            const li = document.createElement('li'); li.append(button(node.doctype + ': ' + node.name, () => open(node))); results.append(li);
        }
        el('record-state').textContent = 'Disconnected, read-only snapshot (claimed date: ' + snapshot.created_at + '). ' + matching.length + ' matching records; showing at most ' + MAX_RESULTS + '. Permissions are not rechecked.';
    }
    function reset(message) {
        snapshot = null; nodes = new Map();
        el('record-results').replaceChildren(); el('record-info').replaceChildren();
        el('record-type').replaceChildren(new Option('All types', ''));
        el('record-state').textContent = message;
    }
    el('record-file').addEventListener('change', async event => {
        const token = ++generation, file = event.target.files[0];
        reset('Loading local snapshot…');
        try {
            if (!file || file.size > MAX_BYTES) throw Error('Invalid file');
            const data = JSON.parse(await file.text());
            const index = validate(data);
            if (token !== generation) return;
            snapshot = data; nodes = index;
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
