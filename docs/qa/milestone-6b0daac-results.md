# 6b0daac: owner-reported application and fixture results

The owner supplied terminal output from `/home/frappe/frappe-bench/apps/siraj_research`. `git fetch upstream arena/a2663352-siraj-research` succeeded, and the subsequent log showed `05a607e` and `6b0daac` ahead of `4cf349b`. Before the merge, `git status --short` showed the pre-existing workspace JSON modification. The displayed `git merge --ff-only 6b0daac` completed as a fast-forward from `4cf349b`; its file list does not include the modified workspace JSON. No post-merge status was provided, so this record does not assert that one was checked.

| Command | Reported result | Scope |
| --- | --- | --- |
| `python3 -m unittest discover -s tests -p 'test_event_transition_review.py' -v` | **PASSED**: 5 tests, 0.003 s, `OK`; no skips shown | In-memory supplied manifests and metadata only |
| `python3 -m unittest discover -s tests -p 'test_privacy_query_scaling.py' -v` | **PASSED**: 3 tests, 0.119 s, `OK`; no skips shown | Synthetic report stubs and list-call shapes, not SQL or site timings |
| `python3 -m unittest discover -s tests -p 'test_visualization_permission_paths.py' -v` | **PASSED**: 2 tests, 0.005 s, `OK`; no skips shown | Stubbed list/document denials, not real HTTP or Frappe permissions |
| `node tests/test_offline_records.js` | **PASSED**: Node DOM-stub script printed its success message; individual test count not printed | Synthetic viewer test, including unsigned-status regression; not a real browser/device test |

All four commands completed successfully according to the supplied output; no failures or skipped tests are shown. Python and Node were available in that environment; exact versions were not printed in this run. The earlier attempted Python runs before fetching produced **NO TESTS RAN**, and the earlier Node test was the old version; those attempts are not evidence for this milestone. Results at `4cf349b` are separately recorded in `milestone-4cf349b-results.md`.

These results validate only the stated fixtures, not the completeness or correctness of the threat model or Event migration proposal. **Both documents remain proposals awaiting subsequent review**, with no approved real-record export or executable migration. Real-site non-Administrator permissions, Place-tree and report performance, production browser/device behavior, Event inventory, database rollback and any deployment remain **NOT RUN / NOT VERIFIED**. No instructions in this ledger authorize a site operation.
