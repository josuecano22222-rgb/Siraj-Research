# SIRAJ demo dataset (fictional, removable)

A built-in, **fictional** dataset that makes a fresh site come alive:
people, institutions, locations, events, sources, a three-level military
order of battle, relationships at every confidence level, and the
Phase‑0 family tab — all flagged `[DEMO]` and removable in one command.

> كل السجلات في مجموعة البيانات التجريبية **متخيَّلة** (أشخاص ومؤسسات
> وأحداث من نسج الخيال)، موسومة بـ `[DEMO]`، ويمكن حذفها بأمر واحد.

## Commands (on your server)

```bash
# load (idempotent — safe to re-run)
bench --site frappe.com siraj-research load-demo-data

# report what demo records exist and how to isolate them
bench --site frappe.com siraj-research isolate-demo-data

# remove every [DEMO] record (leaves your real data untouched)
bench --site frappe.com siraj-research remove-demo-data
```

Equivalent direct execution:

```bash
bench --site frappe.com execute siraj_research.setup.demo_data.seed_demo_data
bench --site frappe.com execute siraj_research.setup.demo_data.teardown_demo_data
bench --site frappe.com execute siraj_research.setup.demo_data.demo_status
```

If an older build's demo data is on the site, run `remove-demo-data`
once first — the tag sweep cleans legacy records too — then load.

## What's inside

| Block | Volume | Showcases |
|---|---|---|
| Persons | 25 | military + civilian, six unit commanders, **family tab** (spouse/children/grandchildren → `is_grandparent`; one explicit Single) |
| Institutions | 8 | bilingual names, types, honest founding precision |
| Places | 12 | real geography, exact coordinates |
| Events | 15 | 15 Siraj Event rows: 9 date-precision showcase + 6 desk flagship (status + linked place) |
| Sources | 10 | k01 = **master demo source cited by every record** |
| Military units | 6 | Division → Brigade → Battalion (3 levels), commanders linked, subtree personnel derived |
| Relationships | 24 | all six confidence codes, directed + symmetric, person↔org, person↔event, unit↔place, cites |
| Link-table rows | 36 | Person↔Institution, Person↔Event, Siraj Event↔Person/Location/Institution/Unit, … |

### Edge cases (deliberate)

- **Auto-fill demo** — `Al-Amal Research Campus` carries coordinates
  only; on save the hierarchy auto-fills from your imported geography
  (unresolvable levels stay empty, as designed).
- **Missing levels** — `Ministry Quarter Annex` knows its country and
  nothing else: the search reply lists the gap in `missing_levels`.
- **Open water** — `Mediterranean offshore station` at exactly
  `31.6, 33.8` (never rounded): no admin level resolves; map search
  reports it as not on land.
- **Uncertain dates** — a `circa 1947` event with precision
  `approximate`, a `1960s` event with precision `decade`, and a person
  born `circa 1947` with precision `uncertain`.

## How removal stays precise

1. **Manifest** — load writes `siraj_demo_manifest.json` into the site
   folder listing every created document; remove deletes exactly those.
2. **Tag sweep fallback** — anything whose display/title field contains
   `[DEMO]` is removed too (this also cleans datasets from older
   builds). Relationships are matched via their tagged primary source
   because their derived display name embeds series ids.
3. **Orderly deletes** — link tables first, units deepest-first
   (a unit with subordinates refuses to be deleted), sources last.
   Non-demo records that hang off demo records block their deletion and
   are reported instead of force-removed.

## Rules the dataset follows

- **Coordinates are never rounded or shortened** — stored exactly as
  written (mandatory project rule).
- **Fictional only** — no real persons, institutions or events; real
  geography is used solely to demonstrate the coordinate → hierarchy
  auto-fill. A CI guard (`tests/test_demo_data_structure.py`) blocks
  real-world names from leaking in.
- **Idempotent** — every insert is guarded by an existence check;
  re-running load changes nothing.
- **Sourced** — every record ends up with a primary source and at
  least one Evidence row (`source → every claim`).

## Tests

```bash
# pure contracts (CI, no site needed)
python -m pytest tests/test_demo_data_structure.py -q

# live round-trip on the server
bench --site frappe.com run-tests --module siraj_research.tests.test_demo_data
```

---

# مجموعة البيانات التجريبية (متخيَّلة وقابلة للإزالة)

مجموعة مدمجة **متخيَّلة** تُحيي الموقع الجديد: أشخاص ومؤسسات ومواقع
أحداث ومصادر وترتيب قوى من ثلاث طبقات وعلاقات بدرجات ثقة مختلفة
وخاصية شجرة العائلة — كلها موسومة `[DEMO]` وتُحذف بأمر واحد.

## الأوامر (على خادمك)

```bash
bench --site frappe.com siraj-research load-demo-data      # تحميل (آمن للتكرار)
bench --site frappe.com siraj-research isolate-demo-data   # تقرير العزل
bench --site frappe.com siraj-research remove-demo-data    # إزالة كاملة
```

إن وُجدت بيانات تجريبية من نسخة أقدم فشغّل `remove-demo-data` أولًا
(المسح بالوسوم ينظّف القديم أيضًا) ثم الحمّل.

## المحتوى

| الكتلة | العدد | ما يعرضه |
|---|---|---|
| الأشخاص | 25 | عسكريون ومدنيون، قادة الوحدات الست، **شجرة العائلة** (زوج/أطفال/أحفاد → `is_grandparent`؛ وواحد أعزب صراحة) |
| المؤسسات | 8 | أسماء ثنائية وأنواع ودقّة تأسيس صادقة |
| المواقع | 12 | جغرافيا حقيقية بإحداثيات دقيقة |
| الأحداث | 15 | 9 أحداث بحثية (دقة التواريخ) + 6 أحداث سراج (حالة + مكان مرتبط) |
| المصادر | 10 | k01 = **المصدر التجريبي المرجعي لكل السجلات** |
| الوحدات العسكرية | 6 | فريق ← لواء ← كتيبة (ثلاث طبقات) مع قادة وعدد مشتق |
| العلاقات | 24 | درجات الثقة الست، موجّهة ومتماثلة، شخص↔مؤسسة، شخص↔حدث، وحدة↔مكان، استشهاد |
| صفوف الربط | 36 | شخص↔مؤسسة، شخص↔حدث، حدث↔شخص/مكان/مؤسسة/وحدة… |

### الحالات الحدّية (متعمّدة)

- **التعبئة التلقائية** — `Al-Amal Research Campus` إحداثيات فقط
  وحدها؛ عند الحفظ يمتلئ التسلسل تلقائيًا.
- **مستويات ناقصة** — `Ministry Quarter Annex` يعرف دولته فقط؛ يظهر
  النقص صراحة في `missing_levels`.
- **مياه مفتوحة** — محطة في البحر المتوسط بالضبط `31.6, 33.8`
  (دون تقريب): لا يُحلَّ أي مستوى إداري.
- **تواريخ غير مؤكدة** — حدث `circa 1947` بدقة `approximate`، وحدث
  `1960s` بدقة `decade`، وشخص وُلد `circa 1947` بدقة `uncertain`.

## كيف تبقى الإزالة دقيقة

1. **قائمة تسييل** — التحميل يكتب `siraj_demo_manifest.json` بمجلد
   الموقع بكل الأسماء المُنشأة؛ الإزالة تحذفها بالضبط.
2. **مسح احتياطي بالوسوم** — أي سجل يحمل `[DEMO]` في حقل العرض
   يُحذف أيضًا (ينظّف نسخًا أقدم). العلاقات تُطابَق عبر مصدرها
   الموسوم لأن اسمها المشتق يحمل معرّفات السلاسل.
3. **حذف رتيب** — جداول الربط أولًا، ثم الوحدات من الأعمق (الوحدة
   ذات الأبناء ترفض الحذف وتُبلَّغ بدل فرضه)، والمصادر أخيرًا.

## القواعد

- **لا تقريب أبدًا للإحداثيات** — تُخزَّن كما تُكتب حرفيًا.
- **خيال فقط** — لا أشخاص أو مؤسسات أو أحداث حقيقية؛ الجغرافيا
  الحقيقية للتوضيح فقط. حارس CI يمنع تسرب أسماء حقيقية.
- **آمن للتكرار** — كل إدراج محمي بفحص وجود.
- **مسنَد** — كل سجل ينتهي بمصدر أساسي وصف Evidence واحد على الأقل.

## الاختبارات

```bash
python -m pytest tests/test_demo_data_structure.py -q
bench --site frappe.com run-tests --module siraj_research.tests.test_demo_data
```
