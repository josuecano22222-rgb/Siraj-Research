# -*- coding: utf-8 -*-
"""Jinja helpers for server-rendered surfaces (print formats, reports)."""
from siraj_research.record_icons import record_meta, svg, COLOURS


def siraj_doctype_svg(doctype: str, size: int = 16) -> str:
	"""Inline SVG glyph for ``doctype``."""
	return svg(doctype, size=size)


def siraj_doctype_colour(doctype: str) -> str:
	return record_meta(doctype)["colour"]


def siraj_doctype_pill(doctype: str, label: str | None = None, size: int = 18) -> str:
	"""A coloured pill containing the glyph + label for print/header use."""
	from markupsafe import Markup
	c = siraj_doctype_colour(doctype)
	g = siraj_doctype_svg(doctype, size=size)
	lbl = label or doctype
	return Markup(
		f'<span class="siraj-form-indicator" style="background:{c};display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:999px;color:#fff;font-size:11px;font-weight:600">'
		f'{g}&nbsp;{lbl}</span>'
	)
