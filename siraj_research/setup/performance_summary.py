"""Opt-in, isolated-site direct-function performance aggregation, no HTTP route.

Permission hooks may have side effects
 bench execute can commit. Never run on
working data or without specific approval. Results are not production evidence.
"""

import math
import statistics

from siraj_research.setup.link_query_probe import measure


def run(user, workload, parent=None, *, batches=2, confirm=None):
	"""Aggregate 3-9 direct-function samples, using existing bounded SQL probe.

	Returns counts and quantiles only, never SQL, record IDs, response bodies or
	usernames. Measures calls routed through frappe.db.sql, not full DB/HTTP.
	No concurrency, dataset generation, memory measurement or optimization.
	"""
	if confirm != "ISOLATED-TEST-APPROVED":
		raise ValueError("Explicit isolated test confirmation required")
	if type(batches) is not int or not 1 <= batches <= 3:
		raise ValueError("Batches must be 1 to 3")
	samples = []
	for _ in range(batches):
		result = measure(user, workload, 3, parent, confirm=confirm)
		samples.extend(result["samples"])

	def nearest_rank(values, p):
		ordered = sorted(values)
		return ordered[max(0, math.ceil(p * len(ordered)) - 1)]

	times = [s["elapsed_ms"] for s in samples]
	sql = [s["sql_calls"] for s in samples]
	sql_time = [s["sql_wall_ms"] for s in samples]
	rows = [s["result_rows"] for s in samples]
	return {
		"workload": workload,
		"sample_count": len(samples),
		"elapsed_ms": {"median": statistics.median(times), "p95_nearest_rank": nearest_rank(times, 0.95)},
		"sql_calls": {"min": min(sql), "max": max(sql)},
		"sql_wall_ms": {
			"median": statistics.median(sql_time),
			"p95_nearest_rank": nearest_rank(sql_time, 0.95),
		},
		"result_rows": {"min": min(rows), "max": max(rows)},
		"note": "Direct function only; frappe.db.sql calls only; small-sample p95 is exploratory, not HTTP or a performance guarantee.",
	}
