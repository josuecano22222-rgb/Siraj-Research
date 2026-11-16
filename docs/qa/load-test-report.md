# Application load and performance report

**Status: BLOCKED — no actual load test or timing has been performed.** There is no running bench/database in this workspace, and production load testing is not authorized. Synthetic unit tests, single-browser smoke tests and static code review are not load measurements.

## Candidate workloads and risks (hypotheses, not measured bottlenecks)

- Geographic, relationship and Structures APIs: paged visible-record scans plus document-level permission checks; response serialization and browser rendering grow with records. Offset paging is not a transactionally consistent snapshot; concurrent changes can alter results. Optional relationship evidence loads each visible relationship document (N+1 risk).
- Tree navigation and reports: permission-filtered pages and parent/link checks; output varies with custom permission hooks and user permissions.
- Local tiles: each request checks access, pack metadata and reads SQLite; limits are per IP, not global quotas. Offline area download can issue up to 512 sequential tile requests in its UI; view-only users can request individual tiles outside that UI. Shared NATs and concurrent viewers need measurement.
- Check actual deployed background workers, scheduled jobs, database indexes/slow-query log and other apps; no active SIRAJ scheduler is declared in the reviewed app hook, which does not prove the whole site lacks jobs.

## Measurement plan (not yet executed)

Use only a separately authorized environment with a restore-tested, appropriately anonymized representative dataset and licensed packs. Record exact revision/app and DB versions, topology and resource limits, dataset cardinalities and distribution, user roles, cache state, service/DB configuration, tool/version and test duration. Agree stop thresholds and rollback/incident plan before any test. Capture baseline and a single-variable post-optimization repeat at approved concurrency levels (for example 1, 5, 20 and 50 users only if capacity and authorization allow). Include cold/warm reads, filtered maps, graphs with/without evidence, structure sources, record details, reports, tree navigation, normal map pan/zoom and a bounded area download. Do not use public OSM tile servers for automated load tests.

For each run record requests/second, p50/p95/p99, timeouts and error counts, client/server CPU and memory, DB connections, query counts/slow plans, I/O, queue depth and worker saturation, and any effects on other apps. Redact logs and avoid storing sensitive record values. Results, bottlenecks, changes and comparisons: **NOT RUN / NOT AVAILABLE**. A real Frappe environment and permission to run the agreed workload are required before this task can be verified.
