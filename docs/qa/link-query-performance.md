# Link-query performance: measurement protocol

**Status: hypothesis and preparation; no real performance measurements.** `can_read_link` in commit 60c2809 requires DocType permission, existence, document permission and an exact-name list query. The relationship report caches by unique `(doctype, name)` per execution; tree expansion checks its selected parent. This adds up to one list query per distinct checked existing, document-readable endpoint (plus existence/document checks and custom-hook work). Short-circuiting or Frappe caching can change actual counts. This is not a global per-site cache and does not imply a fixed number of SQL statements per hook. The graph's primary Source check uses its existing visible-node set instead of per-edge queries.

Only in a separately approved representative environment and window, compare parent commit `e42ba8f` and 60c2809 on equivalent restored datasets, versions, indexes, user roles, concurrency and cache conditions. Do not downgrade the working site or disable security to obtain a baseline. Confirm the baseline still exposes the simulated list-hidden link, and never make it accessible to unauthorized users. Exclude other traffic if possible; record it if not. Include relationship reports with repeated endpoints versus many distinct endpoints, and tree expansions across shallow/deep/wide parents. Include list-query hooks, shares and per-document hooks representative of the site. Do not create data on the working site.

Start with one read per case only after explicit authorization; agree service/DB CPU, memory, query-duration, error and concurrency stop limits and recovery contacts beforehand. Scale only as explicitly authorized; browser-side cancellation does not guarantee server cancellation. Capture sanitized route, revision, anonymized role, record/edge counts, unique endpoints, cache state, total SQL count and duration from approved server/database instrumentation, response bytes, client/server duration, error/timeout counts, and CPU/memory/IO/connection pressure. Record p50/p95/p99 only with sufficient repetitions; label single requests as smoke checks. Do not log query values, names, responses or identifiers. Compare both performance and visibility results; a faster query that changes the intended security policy fails. No optimization is currently proposed as safe until the actual hook and sharing semantics are understood.

## Implemented bounded route probes (not run)

After reviewing `load-probe.js`, and only in an authorized window, the existing browser probe can request the relevant paths using the current authenticated session. Load the reviewed script as described in `load-test-report.md`, then start with one request for each approved case:

```js
await sirajLoadProbe('relationship_report', 1, 1)
await sirajLoadProbe('place_tree_root', 1, 1)
// Substitute a real, approved existing parent locally; never share its name.
await sirajLoadProbe('place_tree_parent', 1, 1, 'EXISTING-PLACE-NAME')
```

The report endpoint has an `ignore_prepared_report=1` request flag but site overrides/customizations must be reviewed; failures may cause server-side Error Log writes. Parent identifiers may be retained by browser/proxy/server logs, though the probe's summary omits them. HTTP 200 is not proof of security or identical data. Verify the result privately and capture only aggregate metrics and pass/fail. The probe stops scheduling new calls on first non-200/network/size error; concurrent calls already sent and server processing can continue. Its bounds are client-only. Review the safety plan and test smaller representative workloads before increasing requests. This measures current code; a security-equivalent optimized implementation does not yet exist, so no optimized measurement or comparison can honestly be reported.

The Explorer relationship map (`visualization.relationship_data`) builds a permission-visible Source/node set and checks membership per edge; the 60c2809 primary-source correction itself adds no per-edge `can_read_link` list query. The **separate Entity Relationship Graph report** uses `can_read_link` for endpoint checks, with a per-report cache, and selected-parent Place tree expansion uses it once per request. Relationship-map scans and document permission checks can still be expensive; measure them separately instead of attributing their total latency to the report/tree change.

## Optional server-side SQL-call counter (fixture-tested only)

`link_query_probe.measure` is non-whitelisted, directly invokes the report or tree once to three times as an existing user and counts calls through the current process's `frappe.db.sql`, cumulative SQL-call wall time, function elapsed time and result row counts. The required confirmation string does not prove a site is isolated. It temporarily wraps that process's database method and restores it and the original session user in `finally`. It never returns SQL text, parameter values, record names or response rows. User lookup, session switching and the preliminary report-permission check occur outside the timed SQL wrapper; other database pathways, lazy iteration, query plans, cache effects and server resources may not be counted; timings include instrumentation overhead and are **not HTTP**. The report invocation checks report permission but does not reproduce every query-report wrapper, site override or frontend operation. An error can be logged or have hook side effects. `bench execute` commits on success and Frappe's exception fallback may repeat a failed call; capture the first sanitized error and stop. This helper has only stub tests.

Only on an existing explicitly authorized isolated environment, after review of all effective hooks and agreement on thresholds, the operator can run (replace locally; do not report identifiers):

```bash
bench --site ISOLATED-SITE execute siraj_research.setup.link_query_probe.measure --kwargs '{"user":"EXISTING-USER","workload":"relationship_report","repetitions":1,"confirm":"ISOLATED-TEST-APPROVED"}'
bench --site ISOLATED-SITE execute siraj_research.setup.link_query_probe.measure --kwargs '{"user":"EXISTING-USER","workload":"place_tree","repetitions":1,"parent":"EXISTING-PLACE","confirm":"ISOLATED-TEST-APPROVED"}'
```

Protect shell history, error logs and output; these commands contain account/record identifiers and the row counts may be sensitive. No accounts or records should be created for the test on the working site. Start with one call; do not scale without separate approval. Capture revisions, matching dataset/cache/role/topology, per-run count/time/row count and external CPU/memory/DB telemetry; row-count equality alone does not establish identical authorized results. Stop on error or agreed limits. For baseline comparison, use equivalent separately isolated copies with approved revisions `e42ba8f` and `60c2809`; the helper did not exist in those revisions. An operator may supply the exact same reviewed probe module via a protected external `PYTHONPATH` in both environments without changing either checkout, but this arrangement and module path must first be tested on the isolated copies. Never downgrade or switch the working checkout. The browser probe measures HTTP time separately. No results or optimization claims exist yet.

To make the **same** probe importable in both authorized isolated revisions without switching a checkout, an operator can prepare a fresh private temporary module directory on each isolated host from the reviewed `link_query_probe.py` (the source is this delivery, not the older revision):

```bash
PROBE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/siraj-probe-XXXXXXXX")
cp /home/frappe/frappe-bench/apps/siraj_research/siraj_research/setup/link_query_probe.py "$PROBE_DIR/siraj_link_query_probe.py"
sha256sum "$PROBE_DIR/siraj_link_query_probe.py"
```

Verify both printed digests match before comparing. In each isolated bench, substitute its site and existing account/parent **locally**, and run the same commands with the same `PROBE_DIR` on that host:

```bash
PYTHONPATH="$PROBE_DIR${PYTHONPATH:+:$PYTHONPATH}" bench --site ISOLATED-SITE execute siraj_link_query_probe.measure --kwargs '{"user":"EXISTING-USER","workload":"relationship_report","repetitions":1,"confirm":"ISOLATED-TEST-APPROVED"}'
PYTHONPATH="$PROBE_DIR${PYTHONPATH:+:$PYTHONPATH}" bench --site ISOLATED-SITE execute siraj_link_query_probe.measure --kwargs '{"user":"EXISTING-USER","workload":"place_tree","repetitions":1,"parent":"EXISTING-PLACE","confirm":"ISOLATED-TEST-APPROVED"}'
```

The example source path must refer to the reviewed new probe file, not an older copy; adjust it locally if necessary. `mktemp`/copy create files and Python may write a bytecode cache in the temporary directory; use protected storage under the approved isolated host's policy. No baseline commands should be run on the working site, and no actual results have been collected.

## Synthetic query-shape regression

`tests/test_privacy_query_scaling.py` runs the actual report against Frappe-shaped stubs. Fixtures contain 1, 10 or 1,000 relationships sharing two endpoints, or 500 relationships with 500 distinct Person endpoints. The test asserts one Person and one Place exact-name list call for repeated endpoints, versus 500 Person and one Place calls for 500 unique endpoints; 1,000 relationships require six stub relationship list pages because the report requests one final empty page when the count is an exact multiple of 200. It also asserts list-hidden endpoints are omitted even if document permission allows them. These are counts of stubbed `get_list` calls, **not SQL counts, real latency, optimized benchmarks or real Frappe security evidence**. The Place tree and snapshot negative cases are covered separately by stubs; approved real-role/direct API tests remain required. Candidate batching might reduce repeated queries but must preserve user permissions, list hooks, shares and error semantics; no optimization has yet been measured or implemented.
