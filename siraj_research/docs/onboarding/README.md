# SIRAJ guided onboarding — tutorial index

Ten steps in dependency order take you from an empty site to a searched,
mapped, sourced registry. Every step gives you a goal, the prerequisites,
a field-by-field explanation (meaning, required/optional, formats, common
mistakes), a worked example, and a validation checkpoint (“you should now
see…”) before linking to the next step.

Each file is **bilingual**: the English guide first, then the same guide
in العربية. The in-app checklist (workspace → *Getting started*, the
Module Onboarding *SIRAJ Research Setup*) mirrors these steps — the
`Onboarding Step` records are kept in sync with this tutorial.

## Before you begin

Open the **SIRAJ Research workspace** (`/app/siraj-research`). The
workspace groups every DocType into sections with live counts, and the
onboarding checklist sits at the top. Everything below is driven from
here. *(In-app record: “Open the SIRAJ workspace”.)* The checklist
carries **14 records**: the ten steps below plus the framing entries
(workspace, settings, geo settings, geographic import) and the closing
quality review.

**Coverage (v2.0.0).** The shipped hierarchy, boundary and gazetteer data
covers **Israel and Palestine (IL/PS) only**. Coordinates anywhere on Earth
are stored and displayed exactly as entered (never rounded), but
place/boundary matches outside IL/PS return nothing until you import data
for your region — see [map-search.md](../map-search.md).

## The ten steps

| # | Step | In-app record(s) | File |
|---|---|---|---|
| 1 | Settings — language, defaults, offline data, map data, roles | Configure SIRAJ Settings · Configure Geo Settings | [01-settings.md](01-settings.md) |
| 2 | Locations — hierarchy and coordinate auto-fill | Import a geographic dataset · Add a Place | [02-locations.md](02-locations.md) |
| 3 | Sources — reliability rating | Create your first Source | [03-sources.md](03-sources.md) |
| 4 | Individuals — family links | Register a Person | [04-individuals.md](04-individuals.md) |
| 5 | Organizations | Add an organization | [05-organizations.md](05-organizations.md) |
| 6 | Military units — unit → parent, affiliation, location, commander | Add a military unit | [06-military-units.md](06-military-units.md) |
| 7 | Events — date precision, location, participants, sources | Add an event | [07-events.md](07-events.md) |
| 8 | Relationships — types, direction, date range, confidence, source | Add a relationship | [08-relationships.md](08-relationships.md) |
| 9 | Other essential data — tags, documents, attachments, import/export | Set up imports and supporting data | [09-supporting-data.md](09-supporting-data.md) |
| 10 | Searching everything, including the map | Try the map search | [10-searching.md](10-searching.md) |

After the ten steps: [common-errors.md](common-errors.md) (what usually
goes wrong and how to fix it) and [quick-reference.md](quick-reference.md)
(the one-page card). The in-app checklist closes with *Review data
quality* — the tutorial’s quality loop is section “Keep the data clean”
in step 9.

## Fresh vs upgraded sites

The `Onboarding Step` and `Module Onboarding` records ship as app JSON
and are upserted by `bench migrate` on every install and upgrade, so the
checklist matches this tutorial on both. If your site predates V2.0.0,
run `bench migrate` once after pulling the update.

---

# دليل التهيئة الموجَّه — فهرس الخطوات

خذك خطوة بخطوة من موقع فارغ إلى سجلّ مُبحث ومُرسَّ ومُسنَد: عشر خطوات
بترتيب التبعية. كل خطوة تمنحك هدفًا، والمقدّمات، وشرحًا حقلًا بحقل
(المعنى، إلزامي/اختياري، الصيغ، الأخطاء الشائعة)، ومثالًا عمليًا،
ونقطة تحقق («يجب أن ترى الآن…») مع رابط إلى الخطوة التالية.

كل ملف **ثنائي اللغة**: الدليل بالإنجليزية أولًا، ثم نفسه بالعربية.
قائمة المهام داخل التطبيق (مساحة العمل → *البدء*) تطابق هذه الخطوات —
سجلات *خطوة التهيئة* تُحدَّث مع هذا الدليل.

## قبل أن تبدأ

افتح **مساحة عمل أبحاث السراج** (`/app/siraj-research`). تجمع المساحة
كل أنواع المستندات في أقسام بعدّادات حيّة، وقائمة المهام في الأعلى.
(السجل داخل التطبيق: «افتح مساحة عمل السراج».)

**التغطية (الإصدار 2.0.0).** بيانات التسلسل الهرمي والحدود والدلائل
المُضمَّنة تغطي **إسرائيل وفلسطين (IL/PS) فقط**. تُخزَّن الإحداثيات في
أي مكان على الأرض كما أُدخلت تمامًا (دون تقريب)، لكن مطابقة المواقع
والحدود خارج IL/PS لن تُرجع شيئًا حتى تستورد بيانات منطقتك — انظر
[map-search.md](../map-search.md).

## الخطوات العشر

| # | الخطوة | السجل داخل التطبيق | الملف |
|---|---|---|---|
| 1 | الإعدادات — اللغة، الافتراضيات، البيانات دون اتصال، بيانات الخريطة، الأدوار | إعدادات السراج · إعدادات الجغرافيا | [01-settings.md](01-settings.md) |
| 2 | المواقع — التسلسل الهرمي والتعبئة التلقائية للإحداثيات | استيراد مجموعة جغرافية · أضِف مكانًا | [02-locations.md](02-locations.md) |
| 3 | المصادر — تقييم الموثوقية | أنشئ أول مصدر | [03-sources.md](03-sources.md) |
| 4 | الأفراد — روابط العائلة | سجّل فردًا | [04-individuals.md](04-individuals.md) |
| 5 | المؤسسات | أضِف مؤسسة | [05-organizations.md](05-organizations.md) |
| 6 | الوحدات العسكرية — الوحدة→الأعلى، الانتماء، الموقع، القائد | أضِف وحدة عسكرية | [06-military-units.md](06-military-units.md) |
| 7 | الأحداث — دقة التاريخ، الموقع، المشاركون، المصادر | أضِف حدثًا | [07-events.md](07-events.md) |
| 8 | العلاقات — الأنواع، الاتجاه، نطاق التاريخ، الثقة، المصدر | أضِف علاقة | [08-relationships.md](08-relationships.md) |
| 9 | البيانات الأساسية الأخرى — الوسوم، المستندات، المرفقات، الاستيراد/التصدير | إعداد الاستيراد والبيانات المساندة | [09-supporting-data.md](09-supporting-data.md) |
| 10 | البحث في كل شيء بما في ذلك الخريطة | جرّب بحث الخريطة | [10-searching.md](10-searching.md) |

بعد الخطوات العشر: [common-errors.md](common-errors.md) (ما يتعارض
عادةً وكيف تصلحه) و[quick-reference.md](quick-reference.md) (بطاقة
صفحة واحدة). تُغلق قائمة المهام داخل التطبيق بـ«مراجعة جودة البيانات» —
حلقة الجودة موضّحة في قسم «حافظ على نظافة البيانات» من الخطوة 9.

## المواقع الجديدة مقابل المُرقَّعة

سجلات *خطوة التهيئة* و*تهيئة الوحدة النمطية* تُشحن كملفات JSON وتُحدَّث
عبر `bench migrate` عند كل تثبيت وترقية، فتتطابق القائمة مع هذا الدليل
في الحالتين. إن كان موقعك أقدم من الإصدار 2.0.0، شغّل `bench migrate`
مرة بعد السحب.
