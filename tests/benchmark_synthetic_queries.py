"""Opt-in local stub benchmark; no network, site, DB, or Frappe.

Run: python3 tests/benchmark_synthetic_queries.py
Counts are stub function calls, not SQL queries
 timing is exploratory only.
"""

import json
import platform
import statistics
import sys
import time

import test_place_tree_synthetic as tree
import test_privacy_query_scaling as report


def timed(fn):
	samples = []
	output = None
	for _ in range(5):
		start = time.perf_counter()
		output = fn()
		samples.append((time.perf_counter() - start) * 1000)
	return output, round(statistics.median(samples), 3)


def run_tree(size):
	case = tree.fixture(size)
	counts = tree.instrument(case)
	rows = case.tree.get_children("Place", "root")
	return {"rows": len(rows), "calls": counts}


def run_report(size, unique):
	counts, rows = report.PrivacyQueryScalingTests().run_report(size, unique)
	return {"rows": len(rows), "calls": counts}


if __name__ == "__main__":
	results = []
	for size in (10, 200, 1000):
		out, elapsed = timed(lambda: run_tree(size))
		results.append({"fixture": "place_children", "size": size, "median_ms": elapsed, **out})
	for size, unique in ((10, 1), (500, 500), (1000, 1)):
		out, elapsed = timed(lambda: run_report(size, unique))
		results.append(
			{
				"fixture": "relationship_report",
				"size": size,
				"unique_person_endpoints": unique,
				"median_ms": elapsed,
				**out,
			}
		)
	print(
		json.dumps(
			{
				"environment": {
					"python": sys.version.split()[0],
					"platform": platform.platform(),
					"timing": "median of 5 in-process fixture construction + invocation runs",
					"scope": "synthetic stub calls; no Frappe or SQL",
				},
				"results": results,
			},
			indent=2,
		)
	)
