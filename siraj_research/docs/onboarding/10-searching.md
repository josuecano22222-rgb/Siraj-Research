# Step 10 — Searching everything, including the map

**Goal.** Find anything — by name, by P-code, by exact coordinate, by
record type — in list views, the global search, and the map search with
its region cascade and “search this area”.

**Prerequisites.** Steps 1–9 (data exists to find); the Siraj Explorer
page (`/app/siraj-explorer`).

**Coverage note (v2.0.0).** Bundled regions, places and boundaries cover
**Israel and Palestine (IL/PS) only** — the examples below use Gaza for
that reason. Exact coordinates anywhere on Earth still resolve and display
without rounding; matches outside IL/PS appear only after you import your
region's data ([map-search.md](../map-search.md)).

---

## 10.1 Where each search lives

| Surface | Best for | Notes |
|---|---|---|
| List-view search boxes | One DocType, known prefix | Frappe standard; Person also matches `family_summary` |
| **Advanced map search widget** (Explorer → Search) | Regions, places, records, coordinates in one box | Full contract: [../map-search.md](../map-search.md) |
| **Region cascade** under the box | Browsing Country → Community without typing | Each selection flies the map to its polygon bbox |
| **Search this area** button | Everything of interest in the current viewport | Antimeridian-safe; type filter applies |
| Explorer record/layer panels | Visual filtering on the map | Record-type chips |

## 10.2 The one-box rules (recap)

- **Minimum 2 characters**, 300 ms debounce.
- **Coordinates:** decimal `31.5, 34.47` or DMS
  `31°31'24.5"N 34°28'12"E` — parsed server-side with exact arithmetic;
  Arabic-Indic digits and ش/ج/ق/غ hemisphere letters accepted. The reply
  echoes **full precision, never rounded**.
- A coordinate answer also returns the **admin chain** (resolved levels
  with P-Codes), **missing levels named explicitly** (an ocean point
  lists all six — not an error), and **nearby** records with distances.
- **Ranking:** P-code exact > name exact > prefix > word > contains;
  coarser levels win ties. Text never fabricates coordinates — a
  swapped order returns an error with a *Use …* suggestion.
- **Scope select:** Everything / Regions / Places / Records; **type
  select** filters records (Person, Institution, Place, Research Event,
  Military Unit, Operational Deployment); **levels** filter regions.

## 10.3 Worked example

1. Open Siraj Explorer → Search.
2. Type `Gaza` → pick the Gaza Strip region → map flies to its bbox.
3. Use the cascade: Country `Palestine, State of` → Governorate
   `Gaza Strip` → District `Gaza` — each pick tightens the view.
4. Type `31.5, 34.47` → chain chips + nearby list appear; click the
   result to jump.
5. Pan over Gaza → **Search this area** → counts for records, places
   and regions in view; switch the type select to `Person` to narrow.

## Validation checkpoint

You should now see: all four result groups (coordinate, regions,
places, records) rendering with their headers; exact strings in
coordinate results; missing levels spelled out; nearby distances in
metres; cascade jumps hitting polygon bboxes; type/level filters
changing the counts; zero `Syntax error in query` lines in the console.

**Common mistakes:** one-character queries (below the minimum);
expecting coordinates from a text query; ignoring the scope select
(wondering why “regions” didn’t appear); rounding coordinates when
typing them (the app never will).

---

## End of the ten steps

→ [common-errors.md](common-errors.md) ·
→ [quick-reference.md](quick-reference.md) ·
→ back to the [index](README.md)

The in-app checklist closes with **Review data quality** — its tutorial
section is [09-supporting-data.md §9.4](09-supporting-data.md).

---

# الخطوة 10 — البحث في كل شيء بما في ذلك الخريطة

**الهدف.** إيجاد أي شيء — بالاسم، برمز P-Code، بإحداثيات دقيقة،
بنوع السجل — في قوائم العرض والبحث العام وبحث الخريطة مع التسلسل
الهرمي و«ابحث في هذه المنطقة».

**المقدّمات.** الخطوات 1–9 (توجد بيانات للعثور عليها)؛ صفحة مستكشف
السراج (`/app/siraj-explorer`).

**ملاحظة التغطية (الإصدار 2.0.0).** المناطق والأماكن والحدود
المُضمَّنة تغطي **إسرائيل وفلسطين (IL/PS) فقط** — ولذلك تستخدم الأمثلة
غزة. الإحداثيات الدقيقة في أي مكان على الأرض تُحلَّل وتُعرض دون تقريب؛
وتظهر المطابقات خارج IL/PS فقط بعد استيراد بيانات منطقتك
([map-search.md](../map-search.md)).

---

## 10.1 أين يعيش كل بحث

| السطح | الأنسب لـ | ملاحظات |
|---|---|---|
| مربعات بقوائم العرض | نوع واحد بادئة معروفة | قياسي؛ Person يطابق أيضًا `family_summary` |
| **مربع بحث الخريطة المتقدم** (مستكشف → Search) | مناطق وأماكن وسجلات وإحداثيات في مربع واحد | العقد الكامل: [../map-search.md](../map-search.md) |
| **التسلسل الهرمي** تحت المتصفح | تصفّح Country → Community بلا كتابة | كل اختيار يطير بمربع حدوده |
| زر **ابحث في هذه المنطقة** | كل ما يهمّ في العرض الحالي | يتحمل خط التاريخ؛ فلتر النوع يسري |
| لوحات المستكشف | تصفّح بصري على الخريطة | شرائح أنواع السجلات |

## 10.2 قواعد المربع الواحد (تذكير)

- **حدّ أدنى حرفان**، إرجاء 300 مللي ثانية.
- **الإحداثيات:** عشري `31.5, 34.47` أو درجات-دقائق-ثوانٍ — تُحلَّل
  على الخادم بدقة حسابية؛ تُقبل الأرقام العربية وش/ج/ق/غ. الرد يعيد
  **دقة كاملة دون تقريب**.
- رد الإحداثيات يشمل **السلسلة الإدارية** (ب P-Codes) و**المستويات
  الناقصة مُسمّاة صراحة** (نقطة محيط تذكر الستة — ليست خطأ) و**أقرب
  الأماكن** بمسافاتها.
- **الترتيب:** P-code مطابق > اسم مطابق > بادئة > كلمة > ضمن؛ الأ粗س
  عند التعادل. النص لا يختلق إحداثيات — تبديل الترتيب يعيد خطأ مع
  اقتراح *Use …*.
- **النطاق:** Everything/Regions/Places/Records؛ **فلتر النوع**
  للسجلات؛ **المستويات** للمناطق.

## 10.3 مثال عملي

1. افتح مستكشف السراج → Search.
2. اكتب `Gaza` → اختر Gaza Strip → تطير الخريطة إلى مربعها.
3. استخدم التسلسل: Country `Palestine, State of` → Governorate
   `Gaza Strip` → District `Gaza` — كل اختيار يضيّق العرض.
4. اكتب `31.5, 34.47` → تظهر رقائق السلسلة وقائمة الأقرب؛ انقر
   للقفز.
5. انقل فوق غزة → **Search this area** → عدّادات السجلات والأماكن
   والمناطق؛ بدّل فلتر النوع إلى `Person` للضيّ.

## نقطة التحقق

يجب أن ترى: المجموعات الأربع (إحداثيات، مناطق، أماكن، سجلات)
برؤوسها؛ نصوص دقيقة في نتائج الإحداثيات؛ المستويات الناقصة مُسمّاة؛
مسافات بالأمتار؛ قفزات التسلسل على مربعات المضلعات؛ الفلاتر تغيّر
العدّادات؛ صفر أخطاء `Syntax error in query` في الكونسول.

**أخطاء شائعة:** استعلامات بحرف واحد؛ توقع إحداثيات من نص؛ إهمال
محدد النطاق («لماذا لا تظهر المناطق؟»)؛ تقريب الإحداثيات عند الكتابة
(التطبيق لن يفعلها أبدًا).

---

## نهاية الخطوات العشر

→ [common-errors.md](common-errors.md) ·
→ [quick-reference.md](quick-reference.md) ·
→ العودة إلى [الفهرس](README.md)

قائمة المهام داخل التطبيق تُغلق بـ«مراجعة جودة البيانات» — قسمها في
الدليل: [09-supporting-data.md §9.4](09-supporting-data.md).
