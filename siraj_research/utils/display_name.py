"""Derive compact, searchable titles for registry records when they are saved."""


def set_display_name(doc, *fields):
	"""Use the first nonblank field. Data columns default to 140 characters."""
	for field in fields:
		value = doc.get(field)
		if value is not None and str(value).strip():
			doc.display_name = str(value).strip()[:140]
			return
	doc.display_name = None


def set_relationship_display_name(doc):
	"""Use stored identifiers rather than fetching potentially restricted links."""
	parts = [doc.get(field) for field in ("subject", "relationship_type", "object")]
	doc.display_name = (
		" → ".join(str(value).strip() for value in parts if value is not None and str(value).strip())[:140]
		or None
	)
