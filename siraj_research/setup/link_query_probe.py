"""Opt-in bench-only query counter for isolated, authorized performance tests.

No HTTP endpoint. It temporarily wraps this process's database sql method and
impersonates one existing user
 custom permission hooks may have side effects.
Never run on a working site without an independently approved load/safety plan.
"""

import time

import frappe


def measure(user, workload, repetitions=1, parent=None, confirm=None):
	"""Measure one existing user's direct report or Place-tree function.

	       Counts calls through frappe.db.sql only
	not necessarily all DB operations.
	       Does not return rows, SQL, account names or parent identifiers. This is not
	       an HTTP end-to-end timing and is not a permission or correctness test.
	"""
	if confirm != "ISOLATED-TEST-APPROVED":
		raise ValueError("Explicit isolated test confirmation required")
	if not isinstance(user, str) or not user.strip() or user == "Guest" or not frappe.db.exists("User", user):
		raise ValueError("Existing non-Guest user required")
	if type(repetitions) is not int or not 1 <= repetitions <= 3:
		raise ValueError("Repetitions must be 1 to 3")
	if workload not in ("relationship_report", "place_tree"):
		raise ValueError("Unsupported workload")
	if workload == "place_tree":
		if not isinstance(parent, str) or not parent.strip() or len(parent) > 140:
			raise ValueError("Existing Place parent required")
	elif parent is not None:
		raise ValueError("Parent is only used for Place tree")
	session_user = frappe.session.user
	original_sql = frappe.db.sql
	sql_count = 0
	sql_time = 0.0

	def counted(*args, **kwargs):
		nonlocal sql_count, sql_time
		sql_count += 1
		start = time.perf_counter()
		try:
			return original_sql(*args, **kwargs)
		finally:
			sql_time += time.perf_counter() - start

	try:
		frappe.set_user(user)
		if workload == "relationship_report":
			if not frappe.has_permission("Relationship", "report"):
				raise PermissionError("Report access denied")
			fn = frappe.get_attr(
				"siraj_research.siraj_research.report.entity_relationship_graph.entity_relationship_graph.execute"
			)

			def invoke():
				return fn()
		else:
			fn = frappe.get_attr("siraj_research.treeview.get_children")

			def invoke():
				return fn("Place", parent)

		frappe.db.sql = counted
		samples = []
		for _ in range(repetitions):
			start = time.perf_counter()
			before_count, before_time = sql_count, sql_time
			result = invoke()
			elapsed = time.perf_counter() - start
			if workload == "relationship_report":
				_, rows = result
			else:
				rows = result
			samples.append(
				{
					"elapsed_ms": round(elapsed * 1000, 2),
					"sql_calls": sql_count - before_count,
					"sql_wall_ms": round((sql_time - before_time) * 1000, 2),
					"result_rows": len(rows),
				}
			)
		return {
			"workload": workload,
			"repetitions": repetitions,
			"samples": samples,
			"note": "SQL calls through frappe.db.sql only; direct server function, not HTTP or security verification.",
		}
	finally:
		frappe.db.sql = original_sql
		frappe.set_user(session_user)
