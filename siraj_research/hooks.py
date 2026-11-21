app_name = "siraj_research"
app_title = "Siraj Research"
app_publisher = "siraj_research"
app_description = "siraj_research"
app_email = "josuecano22222@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

after_install = "siraj_research.setup.install.after_install"
after_migrate = "siraj_research.setup.install.ensure_default_workflow_state"

fixtures = [
	{'dt': 'Print Format', 'filters': [['name', '=', 'SIRAJ Research Dossier']]},
	# the four SIRAJ roles (Del. 8 �4); the DocPerm rows on the DocTypes name them
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"SIRAJ Viewer",
					"SIRAJ Researcher",
					"SIRAJ Reviewer",
					"SIRAJ Administrator",
				],
			]
		],
	},
	{"dt": "Workflow", "filters": [["name", "=", "SIRAJ Review"]]},
	{"dt": "Workflow State"},
	{"dt": "Workflow Action Master"},
]

# Ship Number Cards / Dashboard Charts as module JSON (the workspace's live
# insights widgets). Without this hook the module walk never visits
# number_card/ or dashboard_chart/ for a non-frappe app, so the JSON files
# sit unimported and the workspace widgets reference missing documents.
importable_doctypes = [
	"Number Card",
	"Dashboard Chart",
]

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "siraj_research",
		"logo": "/assets/frappe/images/frappe-framework-logo.svg",
		"title": "Siraj Research",
		"route": "/app/siraj-research",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/siraj_research/css/siraj_research.css"
#
# JS is shipped as a Frappe esbuild bundle so `bench build` rewrites it to
# a content-hashed filename under public/dist/ (any source change → new
# URL → guaranteed cache bust).
#
# CSS is served as fixed /assets paths with an explicit build-stamp query
# string (?v=…). We can't use a CSS bundle because Frappe's postcss2
# esbuild plugin copies only the bundle entry file to a temp directory
# before resolving @import; sibling @import './foo.css' then fails with
# ENOENT (observed 2026-11-17, bench 01471c4→3974662). The ?v= query
# string forces the browser to re-request on every build, which is
# sufficient for CSS (small files, no code split concerns).
from siraj_research.record_icons import SIRAJ_BUILD as _SIRAJ_BUILD

_CSS_VER = "?v=" + _SIRAJ_BUILD
app_include_js = [
	"siraj.bundle.js",
]
app_include_css = [
	"/assets/siraj_research/css/siraj-hierarchy.css" + _CSS_VER,
	"/assets/siraj_research/css/siraj-map-toolbar.css" + _CSS_VER,
	"/assets/siraj_research/css/siraj-icons.css" + _CSS_VER,
	"/assets/siraj_research/css/siraj-map-advanced.css" + _CSS_VER,
	"/assets/siraj_research/css/siraj-profile-fields.css" + _CSS_VER,
]

# Inject per-doctype metadata on every page load so the client has the same
# colour/glyph catalogue the server uses.
boot_session = "siraj_research.record_icons.boot_session"

# include js, css files in header of web template
# web_include_css = "/assets/siraj_research/css/siraj_research.css"
# web_include_js = "/assets/siraj_research/js/siraj_research.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "siraj_research/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Boundary Dataset": "public/js/boundary_dataset.js",
	"Geo Settings": "public/js/geo_settings.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# Standard per-DocType tree scripts live beside their DocType JSON files.
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "siraj_research/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": "siraj_research.jinja_utils",
}

# Installation
# ------------

# before_install = "siraj_research.install.before_install"
# after_install = "siraj_research.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "siraj_research.uninstall.before_uninstall"
# after_uninstall = "siraj_research.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "siraj_research.utils.before_app_install"
# after_app_install = "siraj_research.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "siraj_research.utils.before_app_uninstall"
# after_app_uninstall = "siraj_research.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "siraj_research.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "siraj_research.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "siraj_research.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["siraj_research.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	dt: {"validate": "siraj_research.geo_doc_events.auto_fill_hierarchy"}
	for dt in (
		"Person", "Institution", "Place", "Research Event", "Siraj Event",
		"Military Unit", "Operational Deployment",
	)
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"siraj_research.tasks.all"
# 	],
# 	"daily": [
# 		"siraj_research.tasks.daily"
# 	],
# 	"hourly": [
# 		"siraj_research.tasks.hourly"
# 	],
# 	"weekly": [
# 		"siraj_research.tasks.weekly"
# 	],
# 	"monthly": [
# 		"siraj_research.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "siraj_research.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "siraj_research.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "siraj_research.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["siraj_research.utils.before_request"]
# after_request = ["siraj_research.utils.after_request"]

# Job Events
# ----------
# before_job = ["siraj_research.utils.before_job"]
# after_job = ["siraj_research.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"siraj_research.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
