"""Family-information helpers for the Person DocType (pure, no Frappe import).

Design contract (docs/person-family.md):

* **Spouse, children and grandchildren are person-exclusive** — embedded
  rows that never Link to another Person record, so a person's family
  stays part of their own dossier no matter how the archive grows.
* **Siblings may optionally Link to a Person** — a brother or sister can
  be a research subject in their own right; the link is a convenience,
  not the source of truth.
* Marital status gates the spouse/children/grandchildren sections in the
  UI; hidden fields are *kept*, never cleared — research data survives a
  status change.
* ``is_grandparent`` and ``family_summary`` are derived on save so every
  surface (form, list, Explorer profile) shows the same family picture.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable


def derive_is_grandparent(child_counts: Iterable[int | None]) -> int:
    """Return 1 when any child row reports children of its own."""
    return 1 if any((count or 0) > 0 for count in child_counts) else 0


def build_family_summary(
    data: dict,
    translate: Callable[[str], str] | None = None,
) -> str:
    """One-line family summary, translated at compute time.

    The stored value carries the site language at save time; re-saving
    recomputes it, so a language switch heals on the next edit.
    """
    _ = translate or (lambda s: s)
    parts: list[str] = []
    status = data.get("marital_status") or ""
    spouse = str(data.get("spouse_name") or "").strip()
    if status == "Married":
        parts.append(_("Married"))
        parts.append(_("Spouse: {0}").format(spouse or _("unknown")))
    elif status == "Single":
        parts.append(_("Single"))
    children = int(data.get("children_count") or 0)
    if children:
        parts.append(_("Children: {0}").format(children))
    grandchildren = int(data.get("grandchildren_count") or 0)
    if grandchildren:
        parts.append(_("Grandchildren: {0}").format(grandchildren))
    siblings = int(data.get("siblings_count") or 0)
    if siblings:
        parts.append(_("Siblings: {0}").format(siblings))
    return " · ".join(parts)
