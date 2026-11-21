# Person family fields

The **Family** tab on a Person record captures family data the way research notes do — as part of the person's own file, not as a network of separate records.

## Modelling rule

**Spouse, children, and grandchildren are exclusive to the person's record.** They are embedded rows (`Person Child`, `Person Grandchild` child tables) and are never saved as links to other Person DocTypes — one subject, one file. **Siblings are the exception**: a sibling is often a subject in their own right, so each `Person Sibling` row may optionally link to an existing Person record. The row still keeps its own editable name, so the link is a convenience, never a requirement.

## Marital status gates the UI, not the data

| `marital_status` | What is visible |
|---|---|
| `Single` | Marital status only — the spouse, children, and grandchildren sections are hidden |
| `Married` | Spouse + Children sections appear |
| any + at least one child row has `number_of_children > 0` | The Grandchildren section also appears (`is_grandparent`, derived on save) |

Hidden is **not** cleared: switching back to `Married` restores the previous values, and the server keeps validating whatever rows remain stored. The form adds a dashboard comment when hiding occurs so nobody thinks data was lost.

## Grandchildren's "Through" column

Every grandchild row must say which of this person's children they descend from (`through_child`). The options fill from the Children table client-side; the server rejects any value that is not one of the recorded children. This keeps lineage unambiguous when a person has children from more than one marriage.

## Derived `family_summary`

On every save the server computes a single-line summary, e.g. `Married · Spouse: أمينة الحاج · Children: 2 · Grandchildren: 3 · Siblings: 4`, translated at save time through `_()` so the line matches the site language. It is read-only, stored on the document, and added to `search_fields` — desk search for a spouse's or child's name finds the parent.

## Validation (server-side, `Person.validate_family`)

- Marriage, spouse birth, child, and grandchild dates cannot be in the future.
- The marriage cannot precede the person's birth; a child cannot be born before the person; a grandchild cannot be born before the person or before the child named in `through_child`.
- A row cannot link a Person as their own sibling (`person != self.name`).
- Sibling rows with a link but no name get the linked Person's display name filled in automatically.
- `is_grandparent` and `family_summary` are recomputed on every save — clients never have to keep them in sync.

## Testing

`bench --site frappe.com run-tests --module siraj_research.test_person_family` runs the form-level rules (hidden values preserved, throws, autofill, summary content). Root pytest `tests/test_person_family.py` checks the DocType JSON contracts and the pure helpers in `siraj_research/utils/family.py`.
