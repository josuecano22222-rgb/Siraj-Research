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
    assert 'limit=limit_edges + 1' in SRC, "edge limit must be limit_edges+1"
    print("PASS test_coercion_lines_present")

def test_module_parses():
    ast.parse(SRC); print("PASS test_module_parses")

if __name__ == '__main__':
    test_module_parses(); test_coercion_lines_present()
