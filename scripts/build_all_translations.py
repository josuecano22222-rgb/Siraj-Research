#!/usr/bin/env python3
"""Build final ar.csv by merging the original shipped ar.csv with all new translations
added in this session. Preserves all original translations, adds new ones for 100% coverage.
"""
import csv, json, glob, re
from pathlib import Path

ROOT = Path('/home/user/Siraj-Research')
ar_path = ROOT / 'siraj_research/translations/ar.csv'

# 1. Load existing translations from the shipped ar.csv
existing = {}
with open(ar_path, encoding='utf-8') as f:
    for row in csv.reader(f):
        if not row or len(row) < 2: continue
        existing[row[0]] = row[1]

# 2. New translations added in this session — everything from the consolidated TRANS dict
#    plus the 145 still-missing strings
import importlib.util
spec = importlib.util.spec_from_file_location('bt', ROOT/'scripts/build_translations.py')
bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
existing.update(bt.TRANS)

# 3. Translate the remaining 145 missing strings found above
REMAINING = {
    "Administrative chain broken": "السلسلة الإدارية مكسورة",
    "Age at which the editorial reminder fires for records sitting in In Review. Consumed by the 'SIRAJ · review overdue' Notification condition.":
        "العمر بالأيام الذي يطلق تنبيه المراجعة المتأخرة للسجلات في حالة قيد المراجعة.",
    "Aircraft": "طائرات",
    "An executed mission needs an end date.": "المهمة المنفذة تحتاج تاريخ نهاية.",
    "An optional external code (`military_unit.code UNIQUE`). Kept separate from the document name because a code is reusable business data while `name` is the permanent key.":
        "رمز خارجي اختياري (`military_unit.code UNIQUE`). منفصل عن اسم المستند لأن الرمز قابل لإعادة الاستخدام.",
    "Armored": "مدرع",
    "Assessment without a basis": "تقييم بلا أساس",
    "At most one current deployment per unit (`rules.check_deployment`); the unit's read-only pointer is updated from it.":
        "انتشار جاري واحد كحد أقصى لكل وحدة.",
    "Authentication level": "مستوى التوثيق",
    "Back": "رجوع",
    "Builds the geographic hierarchy: country → governorate → city → quarter. Cycles are rejected by the NestedSet.":
        "يبني السلسلة الجغرافية: دولة → محافظة → مدينة → حي. الحلقات مرفوضة من NestedSet.",
    "Cannot delete": "لا يمكن الحذف",
    "Cannot retire": "لا يمكن الإحالة للتقاعد",
    "Certification": "الاعتماد",
    "Chief of Staff": "رئيس الأركان",
    "Combat": "قتال",
    "Combat / Support / Reserve / Training ⇒ `vocab.CLASS_CATEGORIES`.": "قتال/إسناد/احتياط/تدريب ⇒ `vocab.CLASS_CATEGORIES`.",
    "Commanding Officer": "الضابط الآمر",
    "Communications": "اتصالات",
    "Coordinate precision": "دقة الإحداثيات",
    "Course": "دورة",
    "Data Quality & Verification Summary": "ملخص جودة البيانات والتحقق",
    "Data quality": "جودة البيانات",
    "Dates & capacity": "التواريخ والطاقة",
    "Dates & state": "التواريخ والحالة",
    "Days before a record is 'awaiting review'": "الأيام قبل اعتبار السجل 'بانتظار المراجعة'",
    "Default import mode": "وضع الاستيراد الافتراضي",
    "Default overlays": "التراكبات الافتراضية",
    "Deployment name": "اسم الانتشار",
    "Deployment outside the chain of command": "انتشار خارج التسلسل القيادي",
    "Depth {0}": "عمق {0}",
    "Deputy Commander": "نائب القائد",
    "Description": "الوصف",
    "Description (AR)": "الوصف (بالعربية)",
    "Description (EN)": "الوصف (بالإنجليزية)",
    "Direct personnel cannot be negative.": "لا يجوز أن يكون الأفراد المباشرون سالبين.",
    "Disabled": "معطّل",
    "Disabled values stay on existing records but are not offered for new ones.": "القيم المعطّلة تبقى على السجلات الموجودة ولا تُعرض للجديدة.",
    "Discs": "أقراص",
    "Display name": "الاسم المعروض",
    "Distinguishes a corroborated affiliation from a declared one (the original `affiliation_verified`).": "يميز الانتماء الموثَّق عن المصرَّح به.",
    "Division name": "اسم الفرقة",
    "Documentation level": "مستوى التوثيق",
    "Download politeness delay (ms)": "مهلة التأدب في التنزيل (ملي ثانية)",
    "Download size cap (tiles)": "سقف حجم التنزيل (مربعات)",
    "Download zoom ceiling": "سقف تكبير التنزيل",
    "Drill": "تدريب ميداني",
    "Duplicate armament": "تسليح مكرر",
    "Duplicate current deployment": "انتشار جاري مكرر",
    "Duration (days)": "المدة (بالأيام)",
    "Editorial state, driven by the SIRAJ Review workflow (Draft → In Review → Verified → Published, plus Needs Update / Disputed / Archived / Rejected).":
        "حالة التحرير يحركها سير عمل مراجعة سِراج.",
    "Emblem URL (external)": "رابط الشعار (خارجي)",
    "Emblem description": "وصف الشعار",
    "Empty means the appointment is still open — which is what makes the overlap rule decidable (`rules.check_assignment`).":
        "الفارغ يعني التعيين لا يزال مفتوحاً.",
    "End (as stated)": "النهاية (كما وردت)",
    "End (comparable)": "النهاية (قابلة للمقارنة)",
    "End date": "تاريخ النهاية",
    "End precision": "دقة النهاية",
    "Entity Relationship Graph": "رسم العلاقات بين الكيانات",
    "Entity Type": "نوع الكيان",
    "Event type": "نوع الحدث",
    "Events by Type": "الأحداث حسب النوع",
    "Every division sits in exactly one command region — the source's `division.region_id NOT NULL`.": "كل فرقة تقع في منطقة قيادة واحدة بالضبط.",
    "Evidence": "الأدلة",
    "Evidence (claims this record makes)": "الأدلة (المزاعم التي يقدمها هذا السجل)",
    "Exactly as the source gives it: 1950 · 1950-05 · 1950-05-12 · 1950-05-12T21:45 · 'c. 1850' · '1850s' · '1850?'. Authoritative value; the date field beside it is derived from it.":
        "كما يعطيها المصدر تماماً. القيمة الحجية؛ حقل التاريخ مشتق منها.",
    "Excellent": "ممتاز",
    "Exercise": "مناورة",
    "Exercise name": "اسم المناورة",
    "Export Arabic vocabulary labels": "تصدير تسميات المفردات العربية",
    "Export CSV": "تصدير CSV",
    "Export SVG": "تصدير SVG",
    "External Identifier": "معرّف خارجي",
    "External identifiers": "معرّفات خارجية",
    "Fetched from the governorate so a district can never sit in a country its governorate does not belong to.":
        "تُجلب من المحافظة.",
    "Fifth level: only communities of the chosen village.": "المستوى الخامس: مجتمعات القرية المختارة فقط.",
    "Filters": "مرشحات",
    "Find": "بحث",
    "Find in structure": "بحث في الهيكل",
    "Fit": "ملاءمة",
    "Flow": "تدفق",
    "Folded groups": "مجموعات مطوية",
    "Folded records": "سجلات مطوية",
    "Formation": "تشكيل",
    "Formation date": "تاريخ التشكيل",
    "Fourth level: only villages of the chosen municipality.": "المستوى الرابع: قرى البلدية المختارة فقط.",
    "Frappe's tree convention: a group node is a container and cannot be deployed as a leaf. The source has no such column — its `path`/`depth` text columns lose the distinction — so this is the one field the framework adds to the source's shape.":
        "عقدة المجموعة حاوية ولا تُنشر كورقة.",
    "Free-text locality from an older import that could not be matched to a Governorate or District. Nothing is guessed.":
        "محلية نص حر من استيراد قديم تعذرت مطابقته.",
    "Grouping": "تجميع",
    "Groups": "مجموعات",
    "High / Medium / Low.": "مرتفع/متوسط/منخفض.",
    "How close the point is to the true position.": "مدى قرب النقطة من الموقع الحقيقي.",
    "How much of the date is actually known. 'approximate' keeps c. 1850; 'year' keeps 1850; 'decade' keeps '1850s'; 'minute' keeps a time of day.":
        "مقدار ما هو معروف من التاريخ.",
    "How strongly the record's content is verified.": "مدى قوة التحقق من محتوى السجل.",
    "How the point was obtained": "كيف حُصل على النقطة",
    "How the unit's position sits relative to its headquarters and the terrain around it.": "كيفية وقوع الوحدة بالنسبة لمقرها.",
    "ID": "المعرّف",
    "Identity": "الهوية",
    "Image": "الصورة",
    "Image URL (external)": "رابط الصورة (خارجي)",
    "Image alt text": "النص البديل للصورة",
    "Latitude": "خط العرض",
    "Legend": "المفتاح",
    "Longitude": "خط الطول",
    "Matrix": "مصفوفة",
    "Military Force Structure": "هيكل القوة العسكرية",
    "Place (as stated)": "المكان (كما ورد)",
    "Point source": "مصدر النقطة",
    "Position & evidence": "الموقع والأدلة",
    "Position (this record's own)": "الموقع (خاص بهذا السجل)",
    "Primary source": "مصدر أساسي",
    "Provenance & State": "المصدر والحالة",
    "Record status": "حالة السجل",
    "Records": "سجلات",
    "Regions × Units": "المناطق × الوحدات",
    "Regions — command hierarchy": "المناطق — التسلسل القيادي",
    "Relationships by Type": "العلاقات حسب النوع",
    "Researcher's notes": "ملاحظات الباحث",
    "Rings": "حلقات",
    "Series": "السلسلة",
    "Show or hide data table": "إظهار أو إخفاء جدول البيانات",
    "Significance": "الأهمية",
    "Source & verification": "المصدر والتحقق",
    "Start (as stated)": "البداية (كما وردت)",
    "Start (comparable)": "البداية (قابلة للمقارنة)",
    "Start precision": "دقة البداية",
    "Structure diagram": "مخطط الهيكل",
    "Support": "إسناد",
    "The named place the event happened at.": "المكان المسمى الذي وقع فيه الحدث.",
    "The radius the true position could lie within.": "نصف القطر الذي قد يقع ضمنه الموقع الحقيقي.",
    "Timing & place": "التوقيت والمكان",
    "Title (Arabic)": "العنوان (بالعربية)",
    "Title (English)": "العنوان (بالإنجليزية)",
    "Total Events": "إجمالي الأحداث",
    "Tree": "شجرة",
    "Treemap": "خريطة شجرية",
    "Type": "النوع",
    "Unable to load record details.": "تعذر تحميل تفاصيل السجل.",
    "Uncertainty radius (m)": "نصف قطر عدم التيقن (م)",
    "Units × Operations": "الوحدات × العمليات",
    "Units — command hierarchy": "الوحدات — التسلسل القيادي",
    "When": "متى",
    "Where": "أين",
    "Zoom in": "تكبير",
    "Zoom out": "تصغير",
    # Add any additional missing key mappings for overrides
    "Event": "حدث تقويمي",
    "Research Event": "حدث بحثي",
    "View": "عرض",
}
existing.update(REMAINING)

# 4. Write the merged CSV
with open(ar_path, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['# Arabic translations for Siraj Research'])
    w.writerow(['# Auto-generated; UTF-8, comma-separated.'])
    for k in sorted(existing.keys()):
        w.writerow([k, existing[k]])
print(f'Wrote {len(existing)} unique entries')

# 5. Verify coverage
def skip(s):
    if not s or not isinstance(s,str) or not s.strip(): return True
    s=s.strip()
    if s in ('0','1'): return True
    if re.match(r'^[a-z_][a-z0-9_]*$', s): return True
    ft={'Tab Break','Section Break','Column Break','Table','HTML','Button','Attach','Attach Image','Barcode','Color','Code','Currency','Data','Date','Datetime','Duration','Dynamic Link','Float','Autocomplete','Geolocation','Int','Link','Long Text','Markdown Editor','Password','Percent','Phone','Rating','Read Only','Select','Check','Signature','Small Text','Text','Text Editor','Time','Table MultiSelect'}
    if s in ft: return True
    if s.startswith('frappe.') or s=='URL': return True
    if s.startswith('eval:') or s.startswith('hidden:'): return True
    return False

missing=set()
def add(s):
    if isinstance(s,str) and s.strip() and not skip(s) and s.strip() not in existing:
        missing.add(s.strip())

for jf in sorted(glob.glob(str(ROOT/'siraj_research/siraj_research/doctype/**/*.json'), recursive=True)):
    d=json.load(open(jf,encoding='utf-8'))
    add(d.get('name'))
    for st in d.get('states',[]): add(st.get('title'))
    for a in d.get('actions',[]): add(a.get('label'))
    for l in d.get('links',[]): add(l.get('label'))
    for f in d.get('fields',[]):
        add(f.get('label'))
        if f.get('description'): add(f['description'])
        opts=f.get('options','')
        if isinstance(opts,str) and f.get('fieldtype')=='Select' and opts:
            for o in opts.split('\n'):
                o=o.strip()
                if o and not o.startswith('frappe.') and not o.startswith('EVT-'):
                    add(o)
ws=json.load(open(ROOT/'siraj_research/siraj_research/workspace/siraj_research/siraj_research.json'))
for sec in ['charts','shortcuts','cards','links']:
    for it in ws.get(sec,[]): add(it.get('label'))
js_re=re.compile(r"__\(\s*(?:f?['\"`]([^'\"`]+)['\"`])")
py_re=re.compile(r"""_\(\s*["']([^"']+)["']""")
for jsf in glob.glob(str(ROOT/'siraj_research/**/*.js'),recursive=True):
    if '/vendor/' in jsf: continue
    for m in js_re.finditer(open(jsf,encoding='utf-8',errors='replace').read()): add(m.group(1))
for pyf in glob.glob(str(ROOT/'siraj_research/**/*.py'),recursive=True):
    if '/tests/' in pyf or '/__pycache__/' in pyf: continue
    for line in open(pyf,encoding='utf-8',errors='replace'):
        for m in py_re.finditer(line): add(m.group(1))
for jf in glob.glob(str(ROOT/'siraj_research/siraj_research/dashboard_chart/**/*.json'),recursive=True)+glob.glob(str(ROOT/'siraj_research/siraj_research/number_card/**/*.json'),recursive=True)+glob.glob(str(ROOT/'siraj_research/siraj_research/report/**/*.json'),recursive=True):
    d=json.load(open(jf))
    add(d.get('name')); add(d.get('report_name')); add(d.get('label'))

print(f'Remaining untranslated: {len(missing)}')
for s in sorted(missing)[:50]:
    print(f'  - {s[:140]}')
if len(missing) > 50:
    print(f'  ... and {len(missing)-50} more')
