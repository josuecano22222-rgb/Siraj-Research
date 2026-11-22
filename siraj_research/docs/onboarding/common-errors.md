# SIRAJ — Common errors and how to fix them

> Quick diagnostics for errors seen while entering data, searching, or
> migrating. Matching **Arabic** below each block.

---

## 1. `"" is not a valid color` (console, dashboards)

**Cause.** A Dashboard Chart JSON missing the `color` field.
**Fix (v2.0.0):** all shipped chart JSONs now carry a hex `color`
(palette: boundaries `#126a68`, events `#7a4fa3`, datasets `#5e64a1`,
governorates `#4a6fa5`, places `#8a6d3b`, relationships `#b85c38`).
Redelivered by any `bench migrate` (`after_migrate` re-imports
insight widgets). If you still see it after migrating, another custom
chart is missing `color` — add it.

**العربية.** السبب: JSON لمخطط لوحة بلا حقل `color`. الإصلاح في
v2.0.0: كل مخططاتنا تحوي `color` ستّي؛ يُعاد تسليمها مع أي `bench
migrate`. إن ظهر بعد الترحيل فمخطط مخصّص آخر ناقص — أضِف اللون.

---

## 2. Many `<rect> attribute …: A negative value …` warnings (console)

**Cause.** High-cardinality **Group By** dashboard widgets (dozens of
bars in a narrow card) make the chart library compute a negative slot
width per bar. The browser drops the invalid rect — cosmetic only.
**Fix/avoid:** none required for data integrity. For silence: reduce
the widget’s group cardinality or hide it from the dashboard
(chart JSON `hidden`), or enlarge the card.

**العربية.** السبب: مخططات «حسب فئة» بعدد فئات كبير في بطاقة ضيقة →
عرض شريحة سالب (تُهمل المتصفح؛ تجميلية). المعالجة: خفّض عدد الفئات
أو أخفِ البطاقة أو كبّرها.

---

## 3. `Page … not found` / `Page #close not found` (desk, 404 console)

**Cause.** A click produced the hash route `#close` (the desk’s hash
router looks it up as a page). Not any SIRAJ content — no file in this
app emits `#close`. Typical triggers: a stray anchor/handler on the
page, or an extension.
**Fix:** tell us *where* you clicked; as a stopgap add `preventDefault`
on the offending link, or disable the extension. Harmless otherwise.

**العربية.** السبب: نقرة وَلَّدت المسار `#close` (موجّه الـ hash في
الصَّحيفة يبحث عنه كصفحة). ليست من محتوى SIRAJ. أخبرنا *بمكان* النقرة؛
المُسكّن مؤقت: `preventDefault` أو تعطيل الإضافة. بلا أثر آخر.

---

## 4. Import rejected / zero rows written

**Checks:** row count vs `Maximum rows per import`; mode vs id
semantics (`Update` with ids that don’t exist writes nothing); required
fields reported per row. Fix reported rows and re-run — `Insert or
Update` is idempotent when ids match.

**العربية.** تحقق: عدد الصفوف مقابل السقف؛ وضع الاستيراد مقابل دلالة
المعرّفات؛ الحقول الإلزامية المُبلَّغ عنها. صحّح وأعد — `Insert or
Update` idempotent عند تطابق المعرّفات.

---

## 5. Coordinate search returns an error

| Message | Meaning | Action |
|---|---|---|
| *Need at least 2 characters* | Below minimum | Type 2+ |
| *Please enter … coordinate as latitude, longitude (e.g. 31.5, 34.47) or … DMS* | Not parseable | Use the shown format; Arabic-Indic digits & ش/ج/ق/غ are fine |
| *Use “31.5, 34.47” as latitude, longitude* | You gave lon-first (e.g. `34.47, 31.5`) | Use the suggested order |
| *Latitude must be between −90 and 90* | Out of range | Fix the number — never round it |

A valid coordinate always returns the admin chain; empty levels appear
in `missing_levels` (normal for oceans/coasts).

**العربية.** الرسائل موضحة في الجدول: الحد الأدنى حرفان؛ الصيغة
الصحيحة (تُقبل الأرقام العربية وش/ج/ق/غ)؛ ترتيب العرضшир-عرض؛ المدى
±90/±180. الإحداثية الصالحة تعيد دائمًا السلسلة الإدارية؛ المستويات
الفارغة تظهر في `missing_levels` (طبيعي للمحيطات).

---

## 6. `Syntax error in query` in the console (search)

**Cause.** Numeric two-sided ranges (`between`) on Float fields —
a known MariaDB/MySQL behaviour.
**Fixed in v2.0.0:** the backend converts them to `>=`/`<=`. If you
still see the line: you are on an old pull — update and `bench
migrate`. It never corrupts data.

**العربية.** السبب: نطاق `between` على حقول Float في MariaDB/MySQL.
**مُصلَح في v2.0.0** بتحويله إلى `>=`/`<=`. إن ظهر فأنت على سحب قديم
— حدّث ثم `migrate`. لا يُفسد البيانات.

---

## 7. Hierarchy didn’t auto-fill after coordinates

**Checks:** lat/lon are in the **Geo** block (coordinates in a text
field don’t trigger anything); the site migrated after upgrading
(validator `auto_fill_hierarchy` ships in `hooks.py`); the field isn’t
already occupied (auto-fill never overwrites). Unresolvable levels are
intentionally left empty.

**العربية.** تحقق: الإحداثيات في كتلة Geo لا في حقل نصي؛ تم
`migrate` بعد الترقية؛ الحقل ليس مشغولًا (التعبئة لا تطغى أبدًا)؛
المستويات غير القابلة للتحديد تُترك فارغة عن قصد.

---

## 8. Family fields don’t appear / disappeared

Marital Status gates visibility: **Single** hides spouse/children/
grandchildren, **Married** reveals them. Hidden ≠ cleared — values are
preserved. `is_grandparent` must be ticked for grandparent fields.

**العربية.** الحالة الاجتماعية تتحكم بالعرض: أعزب يُخفي حقول الأسرة،
متزوج يكشفها. **الإخفاء لا يعني المسح** — القيم محفوظة؛ فعّل
`is_grandparent` لحقول الجدّين.

---

## 9. Onboarding steps missing or stale after upgrade

Steps ship as JSON and upsert on `bench migrate`. If a step is missing:
`bench --site <site> migrate`. A cleared step reopens only if its
`is_complete` was reset — the descriptions live in
`docs/onboarding/` (this folder).

**العربية.** الخطوات تصل كـ JSON وتُحدَّث مع `migrate`. ناقصة؟
`migrate`. الوصف الكامل هنا في `docs/onboarding/`.

---

## 10. `bench` / test commands fail with `python: command not found` or wrong module

Server environment quirks (verified on the deployment host):

* use `env/bin/python` (the bench virtualenv), not a system `python`;
* run pytest **inside** `apps/siraj_research` with the CI ignore list;
* run bench tests with a concrete site: `bench --site frappe.com
  run-tests --module siraj_research.tests.test_person_family`.

**العربية.** بيئة الخادم: استخدم `env/bin/python`؛ شغّل pytest داخل
`apps/siraj_research` بقائمة التجاهل المعتادة؛ شغّل اختبارات bench
مع `--site frappe.com` صريح.

---

## Still stuck?

Collect: the exact message, the URL/route, browser console excerpt, and
`bench --site <site> console` output of the failing record — then open
an issue with those attached.

**لم تُحل؟** اجمع: الرالة الحصرية، المسار، مقتطف الكونسول، وطباعة
السجل الفاشل — ثم افتح issue مرفقة بها.
