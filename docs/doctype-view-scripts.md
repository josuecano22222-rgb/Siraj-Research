# DocType view scripts

Frappe v15 automatically discovers standard `<doctype>_tree.js` and `<doctype>_list.js` files beside the DocType JSON when it loads the DocType metadata. No Client Script record or `doctype_tree_js` hook is needed for these files. After updating, clear the site cache and hard-refresh so Frappe reloads the metadata. If workers serve stale hooks or Python code, restart them.

## Tree views

- `doctype/place/place_tree.js`
- `doctype/military_unit/military_unit_tree.js`
- `doctype/command_region/command_region_tree.js`

These configure the native tree UI separately for each tree DocType. An empty virtual root supports no or multiple root records; child queries go to `siraj_research.treeview.get_children`, which restricts DocTypes, applies Frappe list and document read permissions, and pages through visible children. Opening a node uses its document ID rather than its displayed title.

Military Unit nodes show the unit name first, followed by available echelon, status, business code, direct personnel and a secondary ID. The endpoint only returns fields permitted by the current user's Frappe list permissions and does not fetch linked records. Values are HTML-escaped in the tree; missing names fall back to the record ID. These are direct personnel, not the potentially stale stored subtree total. Place and Command Region retain their native title-and-ID presentation.

The generic Frappe tree mutation dialog is disabled because it does not use the declared parent field. The Military Unit tree instead offers **New Military Unit** to users with create access, and **Add child** on group nodes. Both open the standard form; the latter pre-fills `parent_unit` with the node's document ID. Frappe enforces permissions and validation when the form is saved. Place and Command Region trees remain navigation-only; use their normal forms to create records. This tree UI is not the same as the explorer's Structures tab.

Military Unit hierarchy checks and personnel calculations use parent links, not nested-set indexes. Saving or deleting a unit recalculates the affected ancestor totals. The implementation does not repair existing totals globally, serialize concurrent changes to the same hierarchy, or repair historical nested-set indexes. Back up and assess existing hierarchies before bulk migration; test concurrent updates and permissions on a Frappe bench.

## List views

The 15 standalone DocTypes with a `workflow_state` field have their own `<doctype>_list.js`. They display a colored indicator for a small, explicitly defined set of record states, with a native list filter. They do not enforce transitions or create a workflow. Unknown or empty states do not get a custom indicator; an active Frappe workflow may supply its own indicator. All permission, validation and state-transition decisions remain server-side.

Other standalone DocTypes use Frappe's standard List view. Child tables and the SIRAJ Settings Single do not have standalone list or tree views. There is no benefit in generating empty view scripts for those DocTypes, and no calendar, geographic or other specialized view is implied by adding these list settings.

Tests without a bench: `node tests/test_tree_navigation.js`, `node tests/test_list_navigation.js` and `python3 -m unittest discover -s tests -v`. Test separately on a Frappe site with an empty tree, multiple roots, restricted users, more than 20 children, translated titles and the target browser. The tests do not run a real bench.
