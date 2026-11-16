# 4cf349b: owner-reported fixture-test closure

The owner reported a fast-forward from `74b5cf3` to `4cf349b` with the existing local workspace JSON modification present. They subsequently provided the following terminal output (not agent-run and not live Frappe acceptance):

| Command, run from `/home/frappe/frappe-bench/apps/siraj_research` | Expected | Owner-reported actual |
| --- | --- | --- |
| `/home/frappe/frappe-bench/env/bin/python -m unittest discover -s tests -p 'test_signed_offline_snapshot.py' -v` | 3 tests; `OK`; none skipped | 3 passed, `OK`, 0.102 s, no skips |
| `python3 -m unittest discover -s tests -p 'test_event_schema_compare.py' -v` | 3 tests; `OK` | 3 passed, `OK`, 0.000 s |
| `node tests/test_signed_snapshot_crypto.js` | One synthetic WebCrypto test script success message | Success message reported; no individual test count is printed |
| `node tests/test_offline_records.js` | One synthetic Node DOM-stub test script success message | Success message reported; no individual test count is printed |

All four were **PASSED** as fixture tests in the owner-reported terminal output. None failed or was skipped; no browser GUI, real Frappe permissions, live records, Event migration, load benchmark, site key provisioning or actual offline export was run/reported. The owner's earlier `jsdom` test did not start (`MODULE_NOT_FOUND`); the Node-only replacement subsequently passed. The workspace JSON modification must remain intact. These observations do not establish production readiness or verify any of the six larger work items.

Dependencies: bench Python's `cryptography` package, Python standard library, and Node with ECDSA P-256 WebCrypto, `atob`, `TextEncoder`/`TextDecoder` and `Object.hasOwn`. The first Python test invokes Node as a subprocess. Their output confirms the needed dependencies worked for these fixture tests; no package installation is required or requested. The exact Python/cryptography versions were not printed in this run. An earlier user output reported Node 20.20.2, but this run did not print a new version. If a rerun reports a missing package, skipped tests or missing Node features, mark that test **SKIPPED / NOT RUN**, report the error and do not install anything without approval.

Python `cryptography` returns DER-encoded ECDSA signatures; the issuer converts `(r,s)` to fixed-width 64-byte `r || s`, which WebCrypto expects for P-256. The Python-to-Node interoperability test passed in the owner's reported run. This does not prove compatibility with every browser/device or that WebCrypto is available in all `file://` contexts; the agent's synthetic Chromium fixture is separate evidence. Signed-body bytes are verified as received, avoiding Python/JavaScript JSON reserialization differences. Cross-language Unicode/canonicalization and policy-distribution requirements are in `offline-security-threat-model.md`.

At `4cf349b`, unsigned v1 files were displayed with an explicit `UNVERIFIED` prefix and used a separate code branch; they were not passed through v3 signature verification. Review then found that v1's attacker-controlled claimed-date text was echoed into the status and could contain the words “Signature verified.” The following correction removes that echo and adds a synthetic regression for switching from signed to unsigned and for a misleading date. This correction is **CORRECTIONS UPLOADED on push / AWAITING LOCAL TESTING**, not evidence that all possible UI spoofing is impossible. An attacker controlling viewer code or trust policy is outside this protection.
