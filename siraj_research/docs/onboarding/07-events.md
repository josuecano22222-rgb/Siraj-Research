# Step 7 — Events

**Goal.** Record an event with honest **date precision**, location,
participants and sources — the hub that people, units, institutions and
places hang off.

**Prerequisites.** Steps 2–6 (hierarchy, a Source, at least one Person);
open `/app/siraj-event`.

---

## 7.1 Field-by-field

| Field | Required | Meaning | Common mistakes |
|---|---|---|---|
| Series | yes | `EVT-.####` / dated | — |
| Display name | — | Canonical label | — |
| Title (Arabic) | **yes** | Arabic title | — |
| Title (English) | — | Parallel title | — |
| **Event type** | **yes** | Link → Event Type registry | Loose “misc” typing |
| **Start (as stated)** | — | Verbatim: `12 Ramadan 1419` / `spring 1948` | Destroying the verbatim form |
| **Start (comparable)** + **precision** | — | Normalized datetime + `exact`/`minute`/`day`/`month`/`year`/`decade`/`app` | Precision `exact` for a season — wrong; use `app` (approximate) |
| End (as stated/comparable/precision) | — | Same pattern; omit for point events | End before start |
| **Place** (record) + Place (as stated) | — | Link to a Place + verbatim locality | Verbatim field duplicating the link |
| Geo block (lat/lon + levels) | — | Exact coordinates → auto-fill (step 2) | Rounding — never |
| Description / Significance | — | What happened; why it matters | Significance containing unsourced claims (use Evidence) |
| **Primary source**, Documentation/Authentication level | — | Provenance (step 3) | — |
| Evidence table | — | supports/contradicts rows with page/timestamp | One Evidence row for five claims — split them |
| Participants | — | Via relationship/person-event links (step 8) | Listing participants only in free text |
| Units/institutions | — | Unit↔event / institution↔event rows | — |

**Date-precision rule of thumb:** you know the day → `day`; only the
month → `month`; only the year → `year`; a season or “circa” → `app`;
a decade → `decade`. The “as stated” string always survives untouched.

## 7.2 Worked example

1. `/app/siraj-event` → New → Title (Arabic) `عملية سيف القدس`
   → Display name `Operation Sword of Jerusalem` → Event type
   `Military operation`.
2. Start (as stated) `12 Ramadan 1419` → comparable `1999-04-27`,
   precision `day` → no end (point event).
3. Coordinates `31.505000000000000`, `34.448000000000000` → Save →
   hierarchy fills; Place as stated `Gaza City`.
4. Primary source = step-3 Source; Evidence row (`supports`,
   page/timestamp `00:14:22`); add your step-4 Person as a participant
   relationship (step 8).

## Validation checkpoint

You should now see: precision badge matching the date (no fake
`exact`); verbatim date preserved next to the comparable one; hierarchy
filled from coordinates; participant and source visible on the record;
the event appearing in map search and the timeline views.

**Common mistakes:** fake precision; deleting the “as stated” string;
coordinates rounded (forbidden); participants buried in Description
instead of linked.

**Next:** [Step 8 — Relationships](08-relationships.md)

---

# الخطوة 7 — الأحداث

**الهدف.** تسجيل حدث بـ**دقة تاريخ** صادقة وموقع ومشاركين ومصادر —
المركز الذي تتعلّق به الأفراد والوحدات والمؤسسات والأماكن.

**المقدّمات.** الخطوتان 2–6 (تسلسل، مصدر، فرد واحد على الأقل)؛ فتح
`/app/siraj-event`.

---

## 7.1 شرح الحقول

| الحقل | إلزامي | المعنى | أخطاء شائعة |
|---|---|---|---|
| Series | نعم | `EVT-.####` | — |
| Display name | — | التسمية المرجعية | — |
| Title (Arabic) | **نعم** | العنوان العربي | — |
| Title (English) | — | عنوان موازٍ | — |
| **Event type** | **نعم** | رابط → سجل أنواع الأحداث | تصنيف متردّد «متنوع» |
| **Start (as stated)** | — | حرّيًا: `12 رمضان 1419` / `ربيع 1948` | إتلاف الصيغة الأصلية |
| **Start (comparable)** + **الدقة** | — | تاريخ موحّد + `exact`/`day`/`month`/`year`/`decade`/`app` | `exact` لفصول — خطأ؛ استخدم `app` |
| End (كما ورد/موحّد/دقة) | — | النمط نفسه؛ اتركه للحدث اللحظي | نهاية قبل بداية |
| **Place** + Place (as stated) | — | رابط Place + محلية حرّة | تكرار الرابط في الحقل الحر |
| كتلة الجغرافيا | — | إحداثيات دقيقة → تعبئة تلقائية | تقريب — ممنوع |
| Description / Significance | — | ما حدث؛ لماذا يهم | ادعاءات بلا سند في Significance (استخدم Evidence) |
| **Primary source** ومستويات التوثيق | — | الإسناد (خطوة 3) | — |
| Evidence | — | صفوف يدعم/يناقض مع صفحة/طابع | صف واحد لخمسة ادعاءات — فرّقها |
| المشاركون | — | عبر روابط حدث↔شخص (خطوة 8) | ذكر المشاركين نصًا فقط |
| الوحدات والمؤسسات | — | صفوف ربط حدث↔وحدة/مؤسسة | — |

**قاعدة الدقة:** تعرف اليوم → `day`؛ الشهر فقط → `month`؛ السنة فقط
→ `year`؛ فصل أو «حوالي» → `app`؛ عقد → `decade`. نص «كما ورد» يبقى
كما هو دائمًا.

## 7.2 مثال عملي

1. `/app/siraj-event` → جديد → Title (Arabic) `عملية سيف القدس`
   → Display name `Operation Sword of Jerusalem` → النوع `Military
   operation`.
2. Start كما ورد `12 رمضان 1419` → موحّد `1999-04-27` دقة `day` →
   بلا نهاية (حدث لحظي).
3. الإحداثيات `31.505000000000000`، `34.448000000000000` → حفظ →
   يمتلئ التسلسل؛ Place as stated `Gaza City`.
4. Primary source = مصدر خطوة 3؛ صف Evidence (`supports`،
   `00:14:22`)؛ أضف شخص خطوة 4 كمشارك (خطوة 8).

## نقطة التحقق

يجب أن ترى: وسم دقة مطابق للتاريخ (لا `exact` وهمي)؛ التاريخ الحرّ
محفوظًا بجوار الموحّد؛ التسلسل ممتلئًا من الإحداثيات؛ المشارك والمصدر
ظاهرين؛ ظهور الحدث في بحث الخريطة والخط الزمني.

**أخطاء شائعة:** دقة وهمية؛ محو نص «كما ورد»؛ إحداثيات مقصوصة
(ممنوع)؛ دفن المشاركين في Description بدل الربط.

**التالي:** [الخطوة 8 — العلاقات](08-relationships.md)
