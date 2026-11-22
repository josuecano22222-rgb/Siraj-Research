# Step 3 — Sources: reliability rating

**Goal.** Register the documents your claims rest on, and rate each one’s
reliability so reviewers can see at a glance how much weight it carries.

**Prerequisites.** Step 1 (defaults understood); you can open
`/app/source` (or Sources in the workspace).

---

## 3.1 The Source record

| Field | Required | Meaning / format | Common mistakes |
|---|---|---|---|
| Series | yes | Naming series `SRC-.####` or dated | — |
| Display name | — | Your short label for lists | Duplicating the full title here makes lists unreadable |
| Source name / title | **yes** | Full title as printed | — |
| Title (Arabic) | — | Arabic title when it exists | Leaving blank for Arabic-only sources loses searchability |
| Source type | **yes** | Link → Source Type (book, archive file, interview, website…) | Choosing “website” for a scanned archive document |
| Publisher | — | Publishing body | — |
| Language | — | Link → Language | — |
| ISBN / ISSN, Archive reference, Web link | — | Identifiers as applicable | Putting the link in the title |
| Publication date (as stated) | — | Verbatim string from the item, e.g. `1948?` or `circa 1960` | — |
| Publication date (comparable) | — | Normalized `Datetime` for sorting/filtering | Never delete the “as stated” value to “fix” the comparable one — they serve different purposes |
| Publication date precision | — | `exact`/`minute`/`day`/`month`/`year`/`decade`/`app` (approximate) | Claiming `exact` for a year-only date |
| Access date | — | When you last consulted it (URLs rot) | — |
| **Reliability assessment** | — | Link → Source Reliability (the rating, next section) | Publishing-claims workflows may require it (step 1 setting) |
| Verification notes | — | What you checked, discrepancies found | Rating a source “high” with no notes |
| Scan / PDF | — | Attach the actual document when you have it | Linking to a URL with no local copy |
| Primary source | — | Link when this source derives from another Source | Leaving the chain empty for derivative works |
| Documentation / Authentication level | — | Links controlling evidence strength | — |
| Record status | — | Workflow state (Draft → In review → Published) | — |
| Researcher’s notes, External identifiers | — | Free text; table of external ids | — |

## 3.2 Reliability rating

**Source Reliability** is a small registry (`label_en`, `label_ar`,
`code`, colour, sort order) — typically something like: `high` →
“Contemporary official record”, `medium` → “Secondary account”,
`low` → “Uncorroborated memoir”. Each Source picks exactly one.

**How to rate:** read the item → note provenance in **Verification
notes** → pick the reliability whose description matches → if you cannot
tell, rate *lower* and say why. Ratings are revisable; history lives in
notes.

Every later claim can point at a Source (Person/Institution/Event/
Relationship `primary_source`, plus the **Evidence** child table where
each row says *supports / contradicts / contextualizes* with a page or
timestamp). That is why this step precedes data entry.

## 3.3 Worked example

1. `/app/source` → New → Title `Gaza District administrative circular,
   1997` → Source type `Archive document` → Publisher `District
   Archives` → Publication date (as stated) `1997`,
   precision `year` → attach the scan → Reliability `high`
   (contemporary official record) → Verification notes: `Seal verified;
   two pages missing` → Save.

## Validation checkpoint

You should now see: the Source listed with its series id; the reliability
badge/label visible; the scan downloadable; `access_date` set for web
sources; and (if you enabled *Require a source before publishing*) an
attempt to publish a claim without this Source correctly blocked.

**Common mistakes:** creating Sources only when forced (do it first);
rating without notes; storing only a URL (archive a copy); confusing the
Source Type with the Reliability rating.

**Next:** [Step 4 — Individuals: family links](04-individuals.md)

---

# الخطوة 3 — المصادر: تقييم الموثوقية

**الهدف.** تسجّل الوثائق التي تستند إليها ادعاءاتك، وقيّم موثوقية كل
واحد منها ليعرف المراجعون وزنها من النظرة الأولى.

**المقدّمات.** الخطوة 1 (الافتراضيات معروفة)؛ القدرة على فتح
`/app/source` (أو «المصادر» في مساحة العمل).

---

## 3.1 سجل المصدر

| الحقل | إلزامي | المعنى/الصيغة | أخطاء شائعة |
|---|---|---|---|
| Series | نعم | سلسلة التسمية | — |
| Display name | — | لسان قصير للقوائم | تكرار العنوان الكامل يجعل القوائم عديمة الفائدة |
| Source name / title | **نعم** | العنوان الكامل كما طُبع | — |
| Title (Arabic) | — | العنوان العربي إن وُجد | إغفاله لمصدر عربي يُضعف البحث |
| Source type | **نعم** | رابط → نوع المصدر (كتاب، أرشيف، مقابلة، موقع…) | اختيار «موقع» لوثيقة أرشيفية ممسوحة |
| Publisher | — | الجهة الناشرة | — |
| Language | — | رابط → اللغة | — |
| ISBN / ISSN، Archive reference، Web link | — | المعرّفات المعمّقة | وضع الرابط في العنوان |
| Publication date (as stated) | — | النص الحر كما في الوثيقة مثل `1948?` أو `حوالي 1960` | — |
| Publication date (comparable) | — | تاريخ موحّد للفرز والتصفية | لا تحذف «كما ورد» لتصحيح الموحّد — لكل منهما وظيفة |
| Publication date precision | — | `exact`/`minute`/`day`/`month`/`year`/`decade`/`app` | ادعاء `exact` لسنة فقط |
| Access date | — | آخر استشارة (الروابط تموت) | — |
| **Reliability assessment** | — | رابط → تقييم الموثوقية (القسم التالي) | workflows النشر قد تطلبه (إعداد الخطوة 1) |
| Verification notes | — | ما تحققت منه واختلافات وجدتها | تصنيف «مرتفع» بلا ملاحظات |
| Scan / PDF | — | أرفق الوثيقة إن توفرت | رابط بلا نسخة محلية |
| Primary source | — | إن اشتق هذا المصدر من مصدر آخر | إغفال السلسلة للأشتقاقية |
| Documentation / Authentication level | — | روابط تتحكم بقوة الدليل | — |
| Record status | — | حالة سير العمل | — |
| Researcher’s notes، External identifiers | — | نص حر؛ جدول معرّفات خارجية | — |

## 3.2 تقييم الموثوقية

**Source Reliability** سجل صغير (`label_en`، `label_ar`، `code`، لون،
ترتيب) — عادة: `high` = «سجل رسمي معاصر»، `medium` = «حساب ثانوي»،
`low` = «مذكرات غير مدعومة». كل مصدر يختار واحدًا بالضبط.

**كيف تقيّم:** اقرأ الوثيقة → دوّق ما تحققت منه في **Verification
notes** → اختر الوصف المطابق → إن لم تكد تفرّق، اصنّف *أدنى* وقل السبب.
التقييم قابل للمراجعة؛ التاريخ في الملاحظات.

كل ادعاء لاحق يستطيع الإشارة إلى المصدر (حقل `primary_source` في
Person/Institution/Event/Relationship، إضافة إلى جدول **Evidence** حيث
كل صف يقول *يدعم / يناقض / يسياق* مع صفحة أو طابع زمني). لهذا تسبق
هذه الخطوة إدخال البيانات.

## 3.3 مثال عملي

1. `/app/source` → جديد → العنوان `Gaza District administrative
   circular, 1997` → النوع `Archive document` → الناشر `District
   Archives` → تاريخ النشر كما ورد `1997` بدقة `year` → أرفق المسح →
   الموثوقية `high` → Verification notes: `Seal verified; two pages
   missing` → حفظ.

## نقطة التحقق

يجب أن ترى: المصدر في القائمة بمعرّف السلسلة؛ وسم/تسمية الموثوقية
ظاهرة؛ الملف المرفق قابل للتنزيل؛ `access_date` مضبوط للمصادر
الويبية؛ وإن فعّلت *Require a source before publishing*، فمحاولة نشر
ادعاء بلا مصدر تُرفض كما ينبغي.

**أخطاء شائعة:** إنشاء المصادر عند الضرورة فقط (أنشئها أولًا)؛ تصنيف
دون ملاحظات؛ حفظ رابط وحده (أرشف نسخة)؛ الخلط بين نوع المصدر و
تقييم الموثوقية.

**التالي:** [الخطوة 4 — الأفراد: روابط العائلة](04-individuals.md)
