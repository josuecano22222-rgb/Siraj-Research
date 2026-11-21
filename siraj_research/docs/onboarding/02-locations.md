# Step 2 — Locations: the hierarchy and coordinate auto-fill

**Goal.** Build the six-level administrative hierarchy (or import it) and
learn the app’s defining trick: type coordinates, save, and watch every
empty hierarchy level fill itself from local data.

**Prerequisites.** Step 1 done — **Active boundary dataset** and **Active
gazetteer dataset** set in Geo Settings, **Create missing hierarchy
records** understood.

---

## 2.1 The hierarchy registry

Six Link doctypes, each child pointing at its parent:

| Level | DocType | Parent field | Extra keys |
|---|---|---|---|
| 1 | Country | — (top) | ISO `code` (ERPNext registry) |
| 2 | Governorate | `country` | `code`, `label_en`, `label_ar`*, `pcode`, `parent_pcode`, `latitude`/`longitude`, `bbox`, `boundary` |
| 3 | District | `governorate` | same pattern |
| 4 | Municipality | `district` | same pattern |
| 5 | Village | `municipality` | same pattern |
| 6 | Community | `village` | same pattern |

*Common fields:* **Code** (your stable id), **English/Arabic labels**
(Arabic is required on registry levels), **Source P-Code** + **Parent
P-Code** (dataset codes, e.g. `PS-GZ`), **Latitude/Longitude** (exact —
never rounded), **Bounding box**, **Boundary** link (polygon),
**Disabled** (hide without deleting), **Source kind**
(Manual/Imported/Online/Verified/Disputed), **Last verified on**.

**You normally do not create these by hand** — they arrive through
*Import a geographic dataset* (the in-app record for this step). Manual
entries are for gaps the dataset does not cover: fill `code`,
`label_en`, `label_ar`, and the parent Link; never invent a name to make
the chain look complete — a missing level stays missing.

Two more registries: **Admin Boundary** (the polygons that power region
search and the map) and **Gazetteer Place** (named places with exact
coordinates). Both are selected as *active datasets* in Geo Settings.

## 2.2 Coordinate auto-fill (the core mechanic)

Every mapped DocType (Person, Place, Institution, Research Event,
Military Unit, …) carries the same geography block:

| Field | Meaning | Notes |
|---|---|---|
| `latitude` / `longitude` | Float, **full precision** | Type the exact value — the app never rounds or shortens coordinates, anywhere |
| `country` … `community` | The six Link levels | Filled on save if empty |
| `place_name` | Free-text locality | Filled from the nearest gazetteer place |
| `geocoding_method` | How the point was obtained | `manual` / `map_pick` / `coordinate_entry` / `gazetteer` / … |
| `geometry_source` | Set to `polygon_resolver` by auto-fill | provenance |
| `geo_precision` | `exact` / `approximate` / `centroid` / `uncertain` | your honesty about the point |
| `coordinate_origin_confirmed` | Confirms a real (0,0) point | legacy guard — (0,0) is ignored unless ticked |

**On save**, the `auto_fill_hierarchy` hook (validate event) resolves the
point against the **local** boundary/gazetteer data first and fills only
**empty** hierarchy fields — it never overwrites what you typed. With
*Create missing hierarchy records* on, a point inside a dataset area that
lacks a level row creates that row locally (flagged as locally created —
never from invented names). Online fallback runs only if you enabled it
in step 1.

The same resolution runs live in the **Siraj Explorer map**: click the
map → lat/lon are exact strings → hierarchy preview appears → apply fills
the open form.

## 2.3 Worked example

1. Ensure step 1’s datasets are active.
2. Create a **Place** → Display name `Field test point` →
   **Latitude** `31.522678211310364`, **Longitude** `34.467321788689634`
   (type them in full — no shortcuts) → **Geo precision** `exact`.
3. Save. The hierarchy block fills: country / governorate / district …
   as far as the local data reaches; deeper levels stay empty.
4. Set **Geocoding method** to `coordinate_entry` if it isn’t already.

## Validation checkpoint

You should now see: hierarchy fields populated **without typing them**;
levels the data can’t resolve left **empty** (never invented);
`geocoding_method` and `geometry_source` set; the exact coordinate
strings unchanged after save; the point findable in map search
(`31.5, 34.47`).

**Common mistakes:** rounding coordinates (forbidden — full precision
always); expecting fills before datasets are active; overwriting a filled
level manually when you meant to change the point (change the
coordinates and clear the level instead); treating (0,0) as data without
ticking `coordinate_origin_confirmed`.

**Next:** [Step 3 — Sources: reliability rating](03-sources.md)

---

# الخطوة 2 — المواقع: التسلسل الهرمي والتعبئة التلقائية للإحداثيات

**الهدف.** بناء التسلسل الهرمي الإداري من ستة مستويات (أو استيراده)
وتعلّم الحيلة الأساسية في التطبيق: اكتب الإحداثيات، احفظ، وشاهد كل
مستوى هرمي فارغ وهو يمتلئ من البيانات المحلية.

**المقدّمات.** اكتملت الخطوة 1 — **Active boundary dataset** و**Active
gazetteer dataset** مضبوطان في إعدادات الجغرافيا، و**Create missing
hierarchy records** معروف.

---

## 2.1 سجل التسلسل الهرمي

ستة أنواع مستندات بروابط، كل طفل يشير إلى أباه:

| المستوى | النوع | حقل الأب | مفاتيح إضافية |
|---|---|---|---|
| 1 | Country | — (الأعلى) | رمز ISO (`code`) |
| 2 | Governorate | `country` | `code`، `label_en`، `label_ar`*، `pcode`، `parent_pcode`، `latitude`/`longitude`، `bbox`، `boundary` |
| 3 | District | `governorate` | نفس النمط |
| 4 | Municipality | `district` | نفس النمط |
| 5 | Village | `municipality` | نفس النمط |
| 6 | Community | `village` | نفس النمط |

*حقول مشتركة:* **Code** (معرفك الثابت)، **التسمية بالإنجليزية والعربية**
(العربية إلزامية على مستويات السجل)، **Source P-Code** و**Parent P-Code**
(رموز المجموعة مثل `PS-GZ`)، **Latitude/Longitude** (دقة كاملة — لا
تقريب أبدًا)، **Bounding box**، رابط **Boundary** (المضلع)، **Disabled**
(إخفاء دون حذف)، **Source kind**، **Last verified on**.

**لا تنشئ هذه يدويًا في العادة** — تصل عبر *استيراد مجموعة جغرافية*
(السجل داخل التطبيق لهذه الخطوة). الإدخال اليدوي لسدّ فجوات لا تغطيها
المجموعة: املأ `code` و`label_en` و`label_ar` ورابط الأب؛ لا تختلق اسمًا
لإكمال السلسلة — المستوى الناقص يبقى ناقصًا.

ومخزنان آخران: **Admin Boundary** (المضلعات التي تغذّي البحث والخريطة)
و**Gazetteer Place** (أماكن مسماة بإحداثيات دقيقة). يُختاران كمجموعة
نشطة في إعدادات الجغرافيا.

## 2.2 التعبئة التلقائية للإحداثيات (الآلية الأساسية)

كل نوع مُرسَّ (Person، Place، Institution، Research Event، Military Unit…)
يحمل كتلة جغرافيا مماثلة:

| المعنى | الصيغة/ملاحظات |
|---|---|
| `latitude` / `longitude` | عشري بدقة كاملة — اكتب القيمة كما هي؛ التطبيق لا يقرّب ولا يقصّر الإحداثيات أبدًا في أي مكان |
| `country` … `community` | الروابط الستة — تُملأ عند الحفظ إن كانت فارغة |
| `place_name` | اسم حر — يُملأ من أقرب مكان في الدليل |
| `geocoding_method` | كيف حُصل على النقطة: `manual` / `map_pick` / `coordinate_entry` / … |
| `geometry_source` | يضبطه الملء على `polygon_resolver` — مصدر الأثر |
| `geo_precision` | `exact` / `approximate` / `centroid` / `uncertain` — صدقك حول النقطة |
| `coordinate_origin_confirmed` | يؤكد أن (0,0) نقطة حقيقية — حارس قديم |

**عند الحفظ**، يعالج خطاف `auto_fill_hierarchy` النقطة ضد **البيانات
المحلية** أولًا ويملأ فقط الحقول **الفارغة** — لا يمس ما كتبته. مع
تفعيل *Create missing hierarchy records*، تُنشأ الصفوف الناقصة محليًا
(بعلم أن مصدرها محلي — لا أسماء مخترعة). الاتصال الاحتياطي يعمل فقط
إن فعّلته في الخطوة 1.

نفس التحديد يعمل حيًّا في **خريطة مستكشف السراج**: انقر الخريطة →
إحداثيات كنصوص دقيقة → معاينة السلسلة → تطبيق يملأ النموذج المفتوح.

## 2.3 مثال عملي

1. تأكد من نشاط المجموعات من الخطوة 1.
2. أنشئ **Place** → الاسم `Field test point` → **Latitude**
   `31.522678211310364` و**Longitude** `34.467321788689634` (اكتبهما
   كاملَين دون اختصار) → **Geo precision** `exact`.
3. احفظ. تمتلئ كتلة التسلسل: country/governorate/district… حتى حدود
   البيانات المحلية؛ الأعمق يبقى فارغًا.
4. اضبط **Geocoding method** على `coordinate_entry` إن لم يكن كذلك.

## نقطة التحقق

يجب أن ترى الآن: حقول التسلسل **امتلأت دون كتابتها**؛ المستويات التي
لا تغطيها البيانات **بقيت فارغة** (لا اختلاق أبدًا)؛ `geocoding_method`
و`geometry_source` مضبوطان؛ نصوص الإحداثيات كما هي بعد الحفظ؛ النقطة
قابلة للبحث في الخريطة (`31.5, 34.47`).

**أخطاء شائعة:** تقريب الإحداثيات (ممنوع — دقة كاملة دائمًا); انتظار
الملء قبل تفعيل المجموعات؛ الكتابة فوق مستوى ممتلئ بدل تغيير النقطة
(غيّر الإحداثيات وامسح المستوى أولًا)؛ اعتبار (0,0) بيانات دون تفعيل
`coordinate_origin_confirmed`.

**التالي:** [الخطوة 3 — المصادر: تقييم الموثوقية](03-sources.md)
