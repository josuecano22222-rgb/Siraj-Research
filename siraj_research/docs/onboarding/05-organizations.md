# Step 5 — Organizations

**Goal.** Register an organization (institution) with bilingual names,
type, dates, geography, and provenance — the node that person↔org and
org↔event relationships later attach to.

**Prerequisites.** Steps 2–4 (sources + hierarchy working); open
`/app/institution`.

---

## 5.1 Field-by-field

| Field | Required | Meaning | Common mistakes |
|---|---|---|---|
| Series | yes | `INS-.####` / dated | — |
| Display name | — | Canonical list label | — |
| Name (Arabic) | **yes** | Arabic name | Leaving empty for Arabic-native orgs |
| Name (English), Name (original) + language | — | Parallel forms; original script preserved | Transliterating the original |
| Abbreviation | — | Short form used in graph labels | Using the abbreviation as the display name |
| **Type of institution** | **yes** | Link → Institution Type | Choosing by acronym instead of actual type |
| Subcategory, Governance system | — | Refinements | — |
| Image / URL / alt text | — | Emblem with alt text for accessibility | Alt text repeating the file name |
| Date of establishment/closure | — | `*_as_stated` + comparable + precision (`exact`…`decade`/`app`) for **both** | Claiming exact day for a year-only founding |
| Place (record), City as stated, Address | — | Link to a Place record + verbatim locality | Duplicating hierarchy data into the address |
| Objectives / Org structure / Research significance | — | Long-text blocks | Putting source quotes here instead of Evidence |
| Current leadership / Founders (as stated) | — | Verbatim attribution | Presenting them as verified facts |
| Website, Official accounts | — | Links table | — |
| Areas of expertise | — | Multi-select table | — |
| **Geo block** (lat/lon + six levels + precision) | — | Exact coordinates → auto-fill on save (step 2); `coordinate_origin_confirmed` guards a real (0,0) | Rounding — never |
| Primary source / Documentation / Authentication / Workflow | — | Provenance (step 3) | — |
| Evidence table, External identifiers | — | Per-claim support; external ids | — |

## 5.2 Worked example

1. `/app/institution` → New → Name (Arabic) `معهد الدراسات
   الاستراتيجية` → Display name `Strategic Studies Institute` →
   Type `Research institute` → founded as stated `1998`,
   comparable `1998-01-01`, precision `year`.
2. Coordinates `31.590000000000000`, `34.470000000000000` → Save →
   hierarchy fills.
3. Primary source = step-3 Source; add one Evidence row
   (`supports`, page `12`).

## Validation checkpoint

You should now see: Arabic name required and saved; type badge on the
list; hierarchy filled from the coordinates with unresolvable levels
left empty; founding year showing `year` precision (not fake-exact);
Evidence row visible under the record.

**Common mistakes:** empty Arabic name; fake date precision; pasting
coordinates rounded to 2 decimals (forbidden); skipping the Source until
“later”.

**Next:** [Step 6 — Military units](06-military-units.md)

---

# الخطوة 5 — المؤسسات

**الهدف.** تسجيل مؤسسة (Institution) بأسماء ثنائية ونوع وتواريخ
وجغرافيا وإسناد — العقدة التي ترتبط بها علاقات شخص↔مؤسسة ومؤسسة↔حدث.

**المقدّمات.** الخطوتان 2–4؛ فتح `/app/institution`.

---

## 5.1 شرح الحقول

| الحقل | إلزامي | المعنى | أخطاء شائعة |
|---|---|---|---|
| Series | نعم | `INS-.####` | — |
| Display name | — | التسمية المرجعية | — |
| Name (Arabic) | **نعم** | الاسم العربي | إغفاله لمؤسسة عربية الأصل |
| Name (English) / (original) + لغة | — | صيغ موازية؛ الأصل يُحفظ | تجويد الأصل |
| Abbreviation | — | الاختصار في تسميات الرسم | اعتماد الاختصار اسمًا رئيسيًا |
| **Type of institution** | **نعم** | رابط → نوع المؤسسة | الاختيار بالاختصار لا بالنوع |
| Subcategory / Governance system | — | تخصيصات | — |
| Image / URL / alt | — | شعار مع نص بديل | نص بديل = اسم الملف |
| تاريخي التأسيس/الإغلاق | — | `*_as_stated` + موحّد + دقة لكليهما | ادعاء يوم مؤكد لسنة فقط |
| Place / City as stated / Address | — | رابط Place + محلية حرّة | تكرار بيانات التسلسل في العنوان |
| Objectives / Org structure / Research significance | — | نصوص طويلة | وضع اقتباسات المصدر هنا بدل Evidence |
| Leadership / Founders (as stated) | — | منسوب حرّيًا | تقديمهما كحقيقة مؤكدة |
| Website / Official accounts / expertise | — | روابط وجداول | — |
| **كتلة الجغرافيا** | — | إحداثيات دقيقة → تعبئة تلقائية (خطوة 2) | تقريب — ممنوع |
| Primary source / مستويات التوثيق / السير | — | الإسناد (خطوة 3) | — |
| Evidence / External identifiers | — | دعم كل ادعاء؛ معرّفات خارجية | — |

## 5.2 مثال عملي

1. `/app/institution` → جديد → Name (Arabic) `معهد الدراسات
   الاستراتيجية` → Display name `Strategic Studies Institute` →
   النوع `Research institute` → تأسيس كما ورد `1998` وموحّد
   `1998-01-01` دقة `year`.
2. الإحداثيات `31.590000000000000`، `34.470000000000000` → حفظ →
   يمتلئ التسلسل.
3. Primary source = مصدر خطوة 3؛ صف Evidence واحد (`supports`، صفحة
   `12`).

## نقطة التحقق

يجب أن ترى: الاسم العربي محفوظًا؛ وسم النوع في القائمة؛ التسلسل
ممتلئًا من الإحداثيات ومستويات غير القابلة للتحديد **فارغة**؛ سنة
التأسيس بدقة `year` (لا وهم يقين)؛ صف Evidence ظاهرًا.

**أخطاء شائعة:** اسم عربي فارغ؛ دقة تواريخ وهمية؛ إحداثيات مقصوصة
لخانتين (ممنوع)؛ تأجيل المصدر «لاحقًا».

**التالي:** [الخطوة 6 — الوحدات العسكرية](06-military-units.md)
