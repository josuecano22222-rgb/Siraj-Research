# Development completion matrix

**Project status: NOT COMPLETE.** The owner's Frappe environment exists but is not directly accessible to the agent. Statuses below concern the requirement as a whole, not just a prototype. Local results are owner-reported unless otherwise stated. No actual site migration, real-record export, signing/encryption-key provisioning or real performance/permission acceptance has been performed here.

| Requirement | Status | Evidence / remaining blocker |
| --- | --- | --- |
| Event collision resolution and core calendar compatibility | Blocked | Research Event still owns the global committed `Event` name; metadata split/consumer refactoring, actual-site dependency inventory, executable migration and tested DB recovery are not complete. In-memory tools are fixture-tested only. |
| Coordinate schema and reversible migration | Blocked | Six committed legacy Float pairs; a read-only aggregate audit is fixture-tested. No approved schema transition, verified typed backup, DB migration or site restore rehearsal. Uncommitted Data-field prototype is excluded from delivery. |
| Offline Explorer records, relationships and Place tree | Partially implemented | Offline map plus identifier/relationship panel and experimental signed snapshots exist; full details/tree integration, production exporter and verified site permissions are not complete. |
| Offline trust, encryption and lifecycle | Blocked | P-256 verifier is fixture-tested only. No approved trust-policy provisioning, encryption, replay prevention, current offline identity or deployment; plaintext copies cannot be remotely revoked. |
| Real Frappe permission testing | Not implemented | Stubbed direct/report/tree/snapshot tests and an Administrator-only permission-decision probe do not establish actual non-admin CRUD/API/shares/hook behavior. Isolated site and separately approved operational tests required. |
| Site performance and load testing | Not implemented | Synthetic Python timings/call counts and bounded probes are not actual Frappe SQL, endpoint or representative before/after results. Controlled isolated dataset and permission matrix required. |
| Imagery and asset licensing | Blocked | Leaflet and Natural Earth/world-atlas package provenance documented; owner-supplied packs, site uploads, branding and inline icon rights remain unverified. No production imagery rights conclusion. |
| Explorer, reports, integration, accessibility and translations | Partially implemented | Synthetic/unit/browser evidence exists; real-site integration, role checks, cross-browser, translation and accessibility acceptance remain outstanding. |
| Installation and upgrade compatibility | Blocked | Event collision, missing legacy patch modules and real-site customizations unresolved. Do not run `bench migrate`, reinstall or deployment without explicit authorization. |
| Aggregate coordinate inventory | Tested with fixtures only | Non-whitelisted read-only helper exists; not run on the owner's site. It may be expensive and `bench execute` has transaction/hook risks; separate isolated-copy approval is needed. |
| Event candidate scanner and rehearsal | Tested with fixtures only | Owner-reported tests at `d660c42` passed. Candidate discovery and classification are not a complete actual-site inventory, DB migration or rollback. |
| Signed offline viewer prototype | Tested with fixtures only | Owner-reported Node suites passed; no actual site export or production key policy. Browser/device and real permission testing still required. |
| Synthetic Place tree/report query models | Tested with fixtures only | Owner-reported stubs passed; timings and call counts are not SQL/Frappe measurements. |
| Administrator-only permission decision probe | Verified in the local Frappe environment **only for that probe's reported decisions** | Owner previously ran the probe for eight DocTypes; Administrator bypass does not establish CRUD or non-admin permission correctness. |

## Owner output through d660c42

The owner supplied successful fast-forward output for `6b0daac..39f77f9` and `39f77f9..d660c42`. `git status --short` after each merge still listed the workspace JSON modification. The owner reported seven Python fixture suites with 8, 6, 6, 5, 5, 3 and 2 tests respectively, all `OK`; Node signature, adversarial signature and DOM-stub viewer scripts all passed. No skips or failures were shown. The committed-source scanner reported 332 text files, 232 unclassified candidates, zero parse errors, zero UTF-8 skips and `execution_ready: false`. It does not inventory the site.

The owner's Python 3.12.3, Linux 6.8.0-149-generic x86_64/glibc 2.39 synthetic benchmark reported Place 10/200/1,000 children: list pages 1/2/6, parent exact-name calls 1 each, document checks 11/201/1,001, exists calls 1 each, median 0.370/1.109/5.969 ms. Report fixtures 10/500/1,000 relationships produced list pages 1/3/6, Person endpoint checks 1/500/1 and Place checks 1 each, median 5.151/88.513/7.922 ms. These include in-process fixture construction over five runs and are not SQL, site latency or authorization evidence.

The preceding initially missing-fetch attempt had three **NO TESTS RAN** results and is not evidence. The subsequent supplied output above supersedes the earlier *awaiting local fixture tests* status for the listed suites only. It does not approve either the Event specification or security threat model; both remain proposals. No conclusion is drawn about tests or Git operations absent from the supplied output.
