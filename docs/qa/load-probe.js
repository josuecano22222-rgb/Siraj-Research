/* Manual, same-origin, bounded read-only load probe. Never runs automatically.
 * Execute only after an explicitly approved test window and safety review.
 * Usage in an authenticated Frappe tab: await sirajLoadProbe('geography', 1, 2)
 * No credentials, response bodies or record identifiers are returned.
 */
(() => {
    'use strict';
    const urls = Object.freeze({
        geography:'/api/method/siraj_research.visualization.geographic_data',
        relationships:'/api/method/siraj_research.visualization.relationship_data',
        structures:'/api/method/siraj_research.visualization.structure_data?source=people',
    });
    const maxBody = 16 * 1024 * 1024, maxTime = 60000;
    async function run(workload, concurrency, requests) {
        if (!Object.hasOwn(urls, workload) || !Number.isInteger(concurrency) || concurrency < 1 || concurrency > 5 ||
            !Number.isInteger(requests) || requests < 1 || requests > 20 || concurrency > requests) throw Error('Invalid workload or limits');
        const controller = new AbortController(), results = [], started = performance.now();
        const timeout = setTimeout(() => controller.abort(), maxTime);
        let next = 0;
        async function one() {
            const start = performance.now(); let status = 'network_error', bytes = 0, reader;
            try {
                const response = await fetch(urls[workload], {credentials:'same-origin', cache:'no-store', redirect:'error', signal:controller.signal});
                status = response.status;
                if (response.body) {
                    reader = response.body.getReader();
                    while (true) {
                        const {done, value} = await reader.read();
                        if (done) break;
                        bytes += value.byteLength;
                        if (bytes > maxBody) { status = 'body_limit'; await reader.cancel(); break; }
                    }
                }
            } catch (error) { status = error.name === 'AbortError' ? 'timeout' : 'network_error'; }
            results.push({status, bytes, ms:performance.now()-start});
        }
        async function worker() {
            while (!controller.signal.aborted) {
                const number = next++;
                if (number >= requests) break;
                await one();
            }
        }
        try { await Promise.all(Array.from({length:concurrency}, worker)); }
        finally { clearTimeout(timeout); }
        const elapsed = (performance.now()-started)/1000, successful = results.filter(r => r.status === 200);
        const sorted = successful.map(r => r.ms).sort((a,b)=>a-b);
        const percentile = p => sorted.length ? Math.round(sorted[Math.ceil(p*sorted.length)-1] * 10) / 10 : null;
        const statuses = {};
        for (const row of results) statuses[String(row.status)] = (statuses[String(row.status)] || 0) + 1;
        return {workload, concurrency, planned_requests:requests, attempted_requests:results.length,
            elapsed_seconds:Math.round(elapsed*100)/100, successful:successful.length, statuses,
            success_per_second:elapsed ? Math.round(successful.length/elapsed*100)/100 : 0,
            p50_ms:percentile(0.50), p95_ms:percentile(0.95), p99_ms:percentile(0.99),
            total_response_bytes:results.reduce((sum,row)=>sum+row.bytes,0), time_limit_reached:controller.signal.aborted};
    }
    window.sirajLoadProbe = run;
})();
