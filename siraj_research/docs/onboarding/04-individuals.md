# Step 4 — Individuals: family links

**Goal.** Register a person with bilingual names, precision-annotated
dates, geography, evidence — and the family block (spouse, children,
grandchildren, siblings) that belongs exclusively to that individual.

**Prerequisites.** Steps 2–3 (a Source exists; hierarchy data imported);
you can open `/app/person`.

---

## 4.1 Identity fields (the ones you touch most)

| Field | Required | Meaning | Common mistakes |
|---|---|---|---|
| Display name | — | Canonical label used in lists/search | Leaving it to auto-naming when you know the better form |
| Name (Arabic) / Name (English) / Name (original) | Arabic name required | Three name representations; original keeps the script as written | Transliterating the original instead of preserving it |
| Original-name language | — | Language of the original form | — |
| Life dates (`*_as_stated` + comparable + precision) | — | Verbatim string **and** normalized date, precision `exact`…`decade`/`app` | Forcing a year-only date to `exact` |
| Marital status | — | `Single` / `Married` — **gates the family block** (below) | Expecting family fields while Single |
| Geo block (lat/lon + six levels) | — | Exact coordinates → auto-fill on save (step 2) | Rounding coordinates — never |
| Primary source, Documentation/Authentication level, Workflow state | — | Provenance (step 3) | — |
| Evidence table | — | Per-claim support: source, supports/contradicts, page | — |

## 4.2 The Family tab

Sits between *Career* and *Evidence* (`tab_family`). Design rule
(locked): **family data is exclusive to this individual** — spouse,
children and grandchildren are values on *this* record, never links to
other Person documents; siblings are name rows (their one Person link
exists only for autofill convenience); `father_person` is the single
Person-Link field.

| Field | Shown when | Notes |
|---|---|---|
| Marital status | always | `Single` hides everything below — **hidden ≠ cleared** (values are kept) |
| Spouse name | Married | Free text |
| Children | Married | Child table (name, optional details) |
| Is grandparent | Married | Must be ticked before grandchildren appear |
| Grandchildren | Married **and** is grandparent | Child table |
| Siblings | always (when family tab visible) | Rows with optional autofill of the sibling’s Person link |
| Father | always | The one Link → Person |
| Family summary | derived | Auto-built: `Married · Spouse: … · Children: n · …` / `Single`; indexed for search |

Validation: a person cannot list themselves as a sibling; sibling rows
autofill their Person link only when empty; hidden fields are never
silently erased.

Full field-level detail: [../person-family.md](../person-family.md).

## 4.3 Worked example

1. `/app/person` → New → Name (Arabic) `أحمد خالد المصري` → Display
   name `Ahmad Khalid al-Masri` → life dates as stated `1952?`,
   comparable `1952`, precision `year`.
2. Coordinates `31.500000000000000`, `34.470000000000000` → Save →
   hierarchy auto-fills (step 2 mechanic).
3. Family tab → Marital status `Married` → Spouse name `Layla
   Hassan` → two Children rows → tick **Is grandparent** → one
   Grandchild row → one Sibling row (Person link autofills) → Save.
4. Set Primary source to your step-3 Source.

## Validation checkpoint

You should now see: family section visible only because status is
Married; switching to Single **hides** but does not erase; family
summary reads `Married · Spouse: Layla Hassan · Children: 2 ·
Grandchildren: 1 · Siblings: 1`; the person appears in search by name
*and* by family summary; hierarchy filled from coordinates.

**Common mistakes:** entering family data while Single (hidden by
design); linking a “child” to another Person instead of a child row;
expecting grandchildren without the grandparent tick; rounding the
coordinates.

**Next:** [Step 5 — Organizations](05-organizations.md)

---

# الخطوة 4 — الأفراد: روابط العائلة

**الهدف.** تسجيل فرد بأسماء ثنائية اللغة وتواريخ بدقة معلَّنة
وجغرافيا وأدلة — ومكتلة العائلة (الزوج/الزوجة، الأحفاد…) التابعة
حصريًا لهذا الفرد.

**المقدّمات.** الخطوتان 2–3 (موجود المصدر؛ بيانات التسلسل مستوردة)؛
القدرة على فتح `/app/person`.

---

## 4.1 حقول الهوية (الأكثر استخدامًا)

| الحقل | إلزامي | المعنى | أخطاء شائعة |
|---|---|---|---|
| Display name | — | التسمية المرجعية في القوائم والبحث | إغفالها والاعتماد على التسمية الآلية |
| Name (Arabic) / (English) / (original) | الاسم العربي إلزامي | ثلاث صيغ للاسم؛ الأصل يُحفظ كما كُتب | تجويد الاسم الأصل بدل حرفه كما هو |
| Original-name language | — | لغة الصيغة الأصلية | — |
| تواريخ الحياة (`*_as_stated` + موحّد + دقة) | — | نص حر **و** تاريخ موحّد، دقة `exact`…`decade`/`app` | إجبار تاريخ بسنة واحدة على `exact` |
| Marital status | — | `Single`/`Married` — **يتحكم بمكتلة العائلة** (أدناه) | توقع حقول عائلة وأنت Single |
| كتلة الجغرافيا (إحداثيات + ستة مستويات) | — | إحداثيات دقيقة → تعبئة تلقائية عند الحفظ (خطوة 2) | تقريب الإحداثيات — ممنوع أبدًا |
| Primary source ومستويات التوثيق وحالة السير | — | الإسناد (خطوة 3) | — |
| جدول Evidence | — | دعم لكل ادعاء: مصدر، يدعم/يناقض، صفحة | — |

## 4.2 تبويب العائلة

يقع بين *Career* و*Evidence*. القاعدة المحكمة: **بيانات العائلة
حصريًا لهذا الفرد** — الزوج/الأحفاد قيم على *هذا* السجل لا روابط إلى
سجلات أخرى؛ الإخوة صفوف أسماء (وصلتهم الوحيدة إلى Person للتعبئة
الآليه فقط)؛ `father_person` هو حقل Person-Link الوحيد.

| الحقل | يظهر عندما | ملاحظات |
|---|---|---|
| Marital status | دائمًا | `Single` يخفي ما بعده — **الإخفاء ≠ المسح** (القيم محفوظة) |
| Spouse name | Married | نص حر |
| Children | Married | جدول صفوف |
| Is grandparent | Married | يجب تفعيله قبل ظهور الأحفاد |
| Grandchildren | Married **و** is grandparent | جدول صفوف |
| Siblings | دائمًا (عند ظهور التبويب) | صفوف مع تعبئة آلية لرابط الشخص إن فارغ |
| Father | دائمًا | الرابط الوحيد → Person |
| Family summary | مُشتق | يُبنى آليًا: `Married · Spouse: … · Children: n` / `Single`؛ مفهرس للبحث |

التحقق: لا يُدرج الشخص نفسه أخًا؛ صفوف الإخوة تُعبَّأ آليًا فقط عند
الفراغ؛ الحقول المخفية لا تُمحى بصمت.

التفصيل الكامل: [../person-family.md](../person-family.md).

## 4.3 مثال عملي

1. `/app/person` → جديد → Name (Arabic) `أحمد خالد المصري` → Display
   name `Ahmad Khalid al-Masri` → تواريخ كما وردت `1952?` وموحّد
   `1952` بدقة `year`.
2. الإحداثيات `31.500000000000000` و`34.470000000000000` → حفظ →
   يمتلئ التسلسل آليًا (آلية خطوة 2).
3. تبويب العائلة → `Married` → اسم الزوجة `Layla Hassan` → صفّا
   أبناء → فعّل **Is grandparent** → صف حفيد → صف أخ (يُعبَّأ الرابط
   آليًا) → حفظ.
4. اضبط Primary source على مصدر خطوة 3.

## نقطة التحقق

يجب أن ترى: قسم العائلة ظاهر *لأن* الحالة Married؛ التحويل إلى Single
**يخفي ولا يمسح**؛ الملخص: `Married · Spouse: Layla Hassan ·
Children: 2 · Grandchildren: 1 · Siblings: 1`؛ ظهور الشخص في البحث
بالاسم *وبالملخص العائلي*؛ التسلسل ممتلئ من الإحداثيات.

**أخطاء شائعة:** إدخال عائلة وأنت Single (مخفية بتصميم)؛ ربط «ابن»
بربط Person بدل صف ابن؛ توقع الأحفاد دون تفعيل الجدّية؛ تقريب
الإحداثيات.

**التالي:** [الخطوة 5 — المؤسسات](05-organizations.md)
