"""Static checks that get_entity_network coerces numeric query args.

We cannot call the real whitelisted endpoint outside a bench, but we can
parse the module and assert the coercion and hard-cap lines exist.
"""
import ast, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC  = (ROOT / 'siraj_research/api/map_relations.py').read_text()

def test_coercion_lines_present():
    assert 'int(limit_nodes' in SRC, "limit_nodes must be coerced to int"
    assert 'int(limit_edges' in SRC, "limit_edges must be coerced to int"
    assert 'MAX_NODES_HARD' in SRC and 'MAX_EDGES_HARD' in SRC, "hard caps must be defined"
    # OR-groups-as-list-of-3-tuples must NOT be passed directly to frappe.get_list
    # (Frappe treats a nested list as a single 4-tuple filter and throws
    # "Filter must have 4 values"); the fix batches via dict filters instead.
    assert 'filters=filt' in SRC or "filters={" in SRC or 'filters=filt,' in SRC, "must use dict filters"
    assert 'subject_type' in SRC and 'object_type' in SRC, "must query both directions"
    # .format() — not comma args — used with _() so {0} is substituted.
    assert '.format(doctype)' in SRC, "doctype must be substituted into the error message"
    print("PASS test_coercion_lines_present")

def test_module_parses():
    ast.parse(SRC); print("PASS test_module_parses")

if __name__ == '__main__':
    test_module_parses(); test_coercion_lines_present()
