# Step 8 — Relationships

**Goal.** Connect records with typed, directed, dated, confidence-tagged,
sourced relationships — person↔person, person↔org, org↔event and the
rest.

**Prerequisites.** Steps 4–7 (at least two records to connect); open
`/app/relationship`.

---

## 8.1 The registries first

**Relationship Type** (`label_en`, `label_ar`, `code`) controls the
vocabulary. Key knobs per type:

| Field | Meaning |
|---|---|
| **Direction** behavior | `is_symmetric` → the relation reads the same both ways (`sibling_of`); otherwise it is directed |
| **Inverse type** | The type seen from the other end (`employs` ↔ `employed_by`) |
| Valid subject/object | Which DocTypes the type may connect (Person → Institution, …) |
| Is hierarchical | Marks parent/child-style types |

Ship defaults exist (family, employment, membership…); add project
specifics rather than free-typing on each record.

## 8.2 The Relationship record

| Field | Required | Meaning | Common mistakes |
|---|---|---|---|
| Series | yes | `REL-.####` / dated | — |
| Display name | — | Auto/derived label | — |
| **Relationship type** | **yes** | Link → Relationship Type | Free-text types (not allowed) |
| **Direction** | — | `Directed` / `Symmetric` | Forgetting direction makes `A manages B` read backwards |
| Ongoing (`is_current`) | — | Relation with no end yet | Leaving end date empty *and* unticking ongoing |
| **Subject type + Subject** | **yes** | Who the relation starts from (Dynamic Link) | Subject/object swapped (direction matters) |
| **Object type + Object** | **yes** | Who it points to | Type mismatch with the relationship type’s allowed types |
| Start (as stated) / comparable / precision | — | Same three-field date pattern as events (`exact`…`app`) | Fake `exact` |
| End (as stated) / comparable / precision | — | Same; empty + **Ongoing** ticked for open relations | Double signals (empty end but ongoing unticked) |
| Relationship description | — | One-line gloss | Restating the type only |
| Role / title (as stated) | — | Verbatim role (`acting commander`) | — |
| **Primary source**, Documentation/Authentication level | — | Provenance (step 3) | Untying the relation from any source |
| Evidence table | — | supports/contradicts with page | — |
| Last review date | — | When a reviewer last confirmed | — |

**Confidence** is expressed with **Authentication level**
(`authentication_level` link: e.g. confirmed / probable / uncertain —
registry from step 9 vocabulary) plus Evidence rows. Lower confidence +
a contradicting Evidence row is a legitimate, saved state — don’t delete
the relation, downgrade it honestly.

## 8.3 Worked example

1. Type check: `employed_by` (directed; subject Person, object
   Institution; inverse `employs`).
2. `/app/relationship` → New → Type `employed_by` → Subject:
   Person `Ahmad Khalid al-Masri` → Object: Institution `Strategic
   Studies Institute` → Start as stated `2005`, comparable
   `2005-01-01`, precision `year` → tick **Ongoing** → Role as stated
   `senior researcher` → Authentication level `confirmed` → Primary
   source = step-3 Source → Save.
3. Add a second relation between the same pair: type `member_of`,
   symmetric semantics as defined by its type.

## Validation checkpoint

You should now see: the relation rendered in the person’s profile and
the relationship graph with the correct arrow direction; inverse type
appearing from the other record’s side; dates with honest precision;
authentication level visible; the relation surviving a re-open exactly
as saved (hidden ≠ cleared logic applies across the app).

**Common mistakes:** swapped subject/object; direction ignored on
directed types; end-date/ongoing contradictions; “confidence” as free
text instead of Authentication level + Evidence.

**Next:** [Step 9 — Other essential data](09-supporting-data.md)

---

# الخطوة 8 — العلاقات

**الهدف.** ربط السجلات بعلاقات مُنمَّطة وموجَّهة ومؤرَّخة ومُصنَّفة
بثقة ومُسنَدة — شخص↔شخص، شخص↔مؤسسة، مؤسسة↔حدث وغيرها.

**المقدّمات.** الخطوتان 4–7 (سجلان للربط على الأقل)؛ فتح
`/app/relationship`.

---

## 8.1 السجلات أولًا

**Relationship Type** (`label_en`، `label_ar`، `code`) يتحكم بالمفردات.
المحرّفات لكل نوع:

| الحقل | المعنى |
|---|---|
| سلوك **الاتجاه** | `is_symmetric` → القراءة متطابقة في الطرفين (`sibling_of`)؛ وإلا فموجَّهة |
| **Inverse type** | النوع من الطرف الآخر (`employs` ↔ `employed_by`) |
| الصنف/الموضوع المسموح | أي أنواع المستندات يصلح الربط |
| Is hierarchical | يميّز أنواع الأب/الابن |

توجد أنواع أساسية مُشحنة (عائلة، توظيف، عضوية…)؛ أضف مشاريعك بدل
الكتابة الحرة في كل سجل.

## 8.2 سجل العلاقة

| الحقل | إلزامي | المعنى | أخطاء شائعة |
|---|---|---|---|
| Series | نعم | `REL-.####` | — |
| Display name | — | تسمية مشتقة | — |
| **Relationship type** | **نعم** | رابط → النوع | أنواع نصية (غير مسموحة) |
| **Direction** | — | `Directed`/`Symmetric` | نسيان الاتجاه يجعل `A manages B` معكوسة |
| Ongoing | — | علاقة بلا نهاية بعد | تاريخ فارغ **و** ongoing غير مفعّل معًا |
| **Subject + نوعه** | **نعم** | من تنطلق العلاقة (Dynamic Link) | تبديل subject/object |
| **Object + نوعه** | **نعم** | إلى من تشير | عدم مطابقة الأنواع المسموحة |
| بدايتها/نهايتها (كما ورد + موحّد + دقة) | — | نمط التواريخ الثلاثي كما في الأحداث | دقة `exact` وهمية |
| Relationship description | — | تعليق سطري | إعادة صياغة النوع فقط |
| Role / title (as stated) | — | دور حرّي (`acting commander`) | — |
| **Primary source** ومستويات التوثيق | — | الإسناد (خطوة 3) | إبقاء العلاقة بلا مصدر |
| Evidence | — | يدعم/يناقض مع صفحة | — |
| Last review date | — | آخر مراجعة | — |

**الثقة** تُعبَّر بـ**Authentication level** (مثلاً confirmed /
probable / uncertain) + صفوف Evidence. ثقة منخفضة + سطر يناقض حالة
مشروعة — لا تحذف العلاقة، اخفضها بصدق.

## 8.3 مثال عملي

1. تحقق من النوع: `employed_by` (موجَّهة؛ موضوع Person؛ كائن
   Institution؛ عكسها `employs`).
2. `/app/relationship` → جديد → النوع `employed_by` → Subject:
   `Ahmad Khalid al-Masri` → Object: `Strategic Studies Institute` →
   البداية كما وردت `2005` وموحّد `2005-01-01` دقة `year` → فعّل
   **Ongoing** → الدور `senior researcher` → Authentication level
   `confirmed` → Primary source = مصدر خطوة 3 → حفظ.
3. أضف علاقة ثانية للزوج نفسه: `member_of` بسلوك نوعها.

## نقطة التحقق

يجب أن ترى: العلاقة مرسومة في ملف الشخص ورسم العلاقات **بسهم
الاتجاه الصحيح**؛ نوع العكس ظاهرًا من السجل الآخر؛ تواريخ بصدق؛
مستوى الثقة ظاهرًا؛ بقاء العلاقة كما حُفظت بعد إعادة الفتح.

**أخطاء شائعة:** تبديل subject/object؛ إهمال الاتجاه؛ تناقض
التاريخ مع Ongoing؛ «ثقة» كنص حر بدل Authentication level + Evidence.

**التالي:** [الخطوة 9 — البيانات الأساسية الأخرى](09-supporting-data.md)
