# SIRAJ Data Model Decisions

## 2026-11-17: Relation DocTypes are STANDARD DocTypes (istable=0), not child tables

### Decision
All many-to-many relationship DocTypes are **standard standalone DocTypes** with:
- `istable=0`, `issingle=0`, `custom=0`
- Proper permissions for all four SIRAJ roles (Viewer/Researcher/Reviewer/Administrator) + System Manager
- `autoname: hash`
- Links to BOTH sides of the relation (e.g., Person Institution has Link `person`→Person AND Link `institution`→Institution)
- Standard fields: `role`, `start_date`, `end_date`, `notes` where appropriate
- Appear in the **Connections panel** of both parents via the parent DocType's `links[]` array
- Accessible as standalone lists (e.g., `/app/person-institution`) for search/reporting/bulk editing
- No Table fields on parents pointing to them (those imply child tables, which don't match the data model)

### Rationale
These relations carry their own attributes (role, date range, notes, evidence, external identifiers, workflow state) and are first-class research objects, not sub-rows of a parent. They must:
- Be independently referenceable (e.g., a Source citing "Person X at Institution Y during 2019-2021")
- Have their own Evidence/External Identifier child tables (child tables cannot themselves have child tables)
- Support their own Workflow state (Draft → Verified → Published)
- Be searchable/listable across all relationships (e.g., "show all affiliations with role 'Commander'")

### DocTypes affected (converted from istable=1 to istable=0)

| Relation DocType | Links to |
|---|---|
| Person Position | Person, Institution, Place |
| Person Institution | Person, Institution |
| Person Event | Person, Siraj Event |
| Person Military Unit | Person, Military Unit |
| Person Location | Person, Place |
| Institution Event | Institution, Siraj Event |
| Institution Military Unit | Institution, Military Unit |
| Institution Location | Institution, Place |
| Military Unit Event | Military Unit, Siraj Event |
| Military Unit Institution | Military Unit, Institution |
| Military Unit Location | Military Unit, Place |
| Siraj Event Person | Siraj Event, Person |
| Siraj Event Institution | Siraj Event, Institution |
| Siraj Event Military Unit | Siraj Event, Military Unit |
| Siraj Event Location | Siraj Event, Place |

### True child tables remain istable=1
These only ever belong to one parent and carry no standalone identity:
- Evidence (on any master doctype)
- External Identifier (on any master doctype)
- Social Account (on Person, Institution)
- Leadership Quality Assessment (on Person)
- Specialization Link (on Person, via Table MultiSelect)
- Expertise Link (on Institution, via Table MultiSelect)
- Unit Armament Holding (on Military Unit)
- Admin Boundary Geom (on Admin Boundary)

### Parent DocTypes
Parent DocTypes (Person, Institution, Military Unit, Place, Siraj Event):
- Do NOT have Table fields pointing at relation DocTypes
- Instead use `links[]` to populate the Connections panel
- Their existing Table fields for Evidence/External Identifiers (true child tables) remain
