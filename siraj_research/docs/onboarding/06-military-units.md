# Step 6 — Military units

**Goal.** Register a unit with its **parent unit** (3-level hierarchy),
**affiliation**, **location** and **commander** — the backbone of the
order-of-battle views.

**Prerequisites.** Steps 2–5 (a Person for commander, hierarchy data);
open `/app/military-unit`.

---

## 6.1 Field-by-field

| Field | Required | Meaning | Common mistakes |
|---|---|---|---|
| Series | yes | `MIL-UNIT-.####` / `MIL-BRG-.####` | — |
| **Unit name** | **yes** | Full designation | Nicknames without the formal name |
| Business code | — | Your internal code | Reusing the same code for two units |
| Group (has subordinates) | — | Tick when it has child units | Ticking it with no children |
| **Parent unit** | — | Link → Military Unit (unit → parent) | Creating a duplicate child instead of linking |
| **Echelon** | **yes** | `Brigade`/`Division`/`Regiment`/`Battalion`/`Company`/… | Echelon contradicting the parent’s (a division under a company) |
| Classification | — | Link → Unit Classification | — |
| Role | — | Function text | — |
| **Commander** | — | Link → **Person** (step 4 record) | Typing a name instead of linking |
| Current deployment | — | Link → Operational Deployment | — |
| **Status** | **yes** | Active/Training/Standby/Mobilized/… | Leaving stale status |
| Direct personnel / Subtree personnel | yes / derived | Headcount: own vs including children | Manually editing subtree (derived) |
| Formation date, Headquarters | — | Date + text | — |
| Armaments table, Emblem | — | Holdings; image with alt | — |
| **Geo block** | — | HQ coordinates → auto-fill (step 2); `linked_place` ties a Place record | Rounding — never |
| Primary source / Documentation / Authentication / Workflow / Evidence | — | Provenance (step 3) | — |

**Affiliation** is expressed through the institution link tables
(unit↔institution) and, for events, unit↔event rows — keep them current
as the record evolves.

## 6.2 Worked example (3-level hierarchy)

1. Create parent: unit name `Northern Command`, echelon `Division`,
   status `Active`, tick **Group** → Save.
2. Create child: unit name `12th Infantry Brigade`, echelon
   `Brigade`, **Parent unit** `Northern Command` → Save.
3. Create grandchild: `3rd Battalion`, echelon `Battalion`, parent
   `12th Infantry Brigade`, **Commander** = your step-4 Person,
   direct personnel `320` → Save.

## Validation checkpoint

You should now see: child listed under its parent (graph/structure view
shows the three levels); `subtree_personnel` derived on the parent;
commander shown as a clickable Person link; HQ coordinates auto-filling
the hierarchy; status badges correct.

**Common mistakes:** orphan units (no parent when one exists);
echelon/parent mismatches; commander as plain text; editing
`subtree_personnel` by hand (it derives from children).

**Next:** [Step 7 — Events](07-events.md)

---

# الخطوة 6 — الوحدات العسكرية

**الهدف.** تسجيل وحدة بـ**الوحدة الأب** (تسلسل من ثلاث طبقات)
و**الانتماء** و**الموقع** و**القائد** — عمود مشاهد ترتيب القوى.

**المقدّمات.** الخطوتان 2–5 (شخص للقائد؛ بيانات تسلسل)؛ فتح
`/app/military-unit`.

---

## 6.1 شرح الحقول

| الحقل | إلزامي | المعنى | أخطاء شائعة |
|---|---|---|---|
| Series | نعم | `MIL-UNIT-.####` | — |
| **Unit name** | **نعم** | التسمية الكاملة | الألقاب بلا الاسم الرسمي |
| Business code | — | رمزك الداخلي | تكرار الرمز لوحدتين |
| Group (has subordinates) | — | فعّل عند وجود أبناء | تفعيله بلا أبناء |
| **Parent unit** | — | رابط → Military Unit | إنشاء ابن مكرر بدل الوصل |
| **Echelon** | **نعم** | `Brigade`/`Division`/… | تناقض الطبقة مع الأب (فرقة تحت فصيلة) |
| Classification / Role | — | تصنيف ووظيفة | — |
| **Commander** | — | رابط → **Person** (سجل خطوة 4) | كتابة اسم بلا ربط |
| Current deployment | — | رابط → Operational Deployment | — |
| **Status** | **نعم** | Active/Training/… | حالة قديمة |
| Direct/Subtree personnel | نعم/مُشتق | عدّاد: الخاص مقابل شامل الأبناء | تعديل الـ subtree يدويًا |
| Formation date / Headquarters | — | تاريخ ونص | — |
| Armaments / Emblem | — | جدول وشعار بنص بديل | — |
| **كتلة الجغرافيا** | — | إحداثيات المقر → تعبئة (خطوة 2)؛ `linked_place` يربط Place | تقريب — ممنوع |
| مصادر وتوثيق وسير وEvidence | — | الإسناد (خطوة 3) | — |

**الانتماء** يُعبَّر عنه بجداول الربط (وحدة↔مؤسسة) و(وحدة↔حدث) —
 حدّثها مع تطور السجل.

## 6.2 مثال عملي (تسلسل ثلاثي)

1. الأب: `Northern Command`، echelon `Division`، `Active`، فعّل
   **Group** → حفظ.
2. الابن: `12th Infantry Brigade`، `Brigade`، **Parent** =
   `Northern Command` → حفظ.
3. الحفيد: `3rd Battalion`، `Battalion`، والده `12th Infantry
   Brigade`، **Commander** = شخص خطوة 4، مباشر `320` → حفظ.

## نقطة التحقق

يجب أن ترى: الابن مدرج تحت أبيه (رسم الهيكل يعرض الطبقات الثلاث)؛
`subtree_personnel` مُشتق للأب؛ القائد كرابط Person قابل للنقر؛
إحداثيات المقر تملأ التسلسل؛ وسوم الحالة صحيحة.

**أخطاء شائعة:** وحدات أيتام (بلا أب عند وجوده)؛ تناقض الطبقة مع
الأب؛ القائد كنص؛ تعديل `subtree_personnel` يدويًا.

**التالي:** [الخطوة 7 — الأحداث](07-events.md)
