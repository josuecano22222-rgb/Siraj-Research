# SIRAJ — One-page quick reference

> Print/keep beside you while entering data. Arabic follows.

---

## The ten steps (goal → shortcut)

| # | Step | You leave with | Shortcut |
|---|---|---|---|
| 1 | Settings | Site language, roles, defaults | `/app/siraj-settings` |
| 2 | Locations | Place records; coordinate → hierarchy | `/app/place`, `/app/governorate` |
| 3 | Sources | Source records + reliability rating | `/app/source`, `/app/source-reliability` |
| 4 | Individuals | Persons + family + marital gating | `/app/person` |
| 5 | Organizations | Institutions (bilingual, typed) | `/app/institution` |
| 6 | Military units | Units with parent + commander | `/app/military-unit` |
| 7 | Events | Events with honest date precision | `/app/siraj-event` |
| 8 | Relationships | Typed, directed, sourced links | `/app/relationship`, `/app/relationship-type` |
| 9 | Supporting data | Tags, evidence, import/export, quality loop | workspace + SIRAJ Settings |
| 10 | Searching | List, global, map search, cascade | `/app/siraj-explorer` |

---

## Dates — the three fields

`…_as_stated` (verbatim, never edited) + `…_comparable` (normalized)
+ `precision`: `exact | minute | day | month | year | decade | app`.
Never claim `exact` you don’t have; `app` = approximately.

## Coordinates — hard rules

* **Never round, shorten, or “tidy” coordinates — ever.** Full
  precision in, full precision out.
* Input: `31.5, 34.47` or `31°31'24.5"N 34°28'12"E` (Arabic-Indic
  digits and ش/ج/ق/غ accepted).
* Put them in the **Geo block** → hierarchy auto-fills empty levels
  only; unresolvable levels stay empty (they show as `missing_levels`
  in search).

## Required-field minimum (save without friction)

| Record | Must have |
|---|---|
| Source | Title, Source type |
| Place | Display name, Place type, Admin level |
| Institution | Name (Arabic), Type |
| Military unit | Unit name, Echelon, Status |
| Siraj event | Title (Arabic), Event type |
| Relationship | Type, Subject, Object |

## Provenance on every claim

`primary_source` + `authentication_level` + an **Evidence** row
(supports/contradicts/contextualizes + page/timestamp). Untied claims
won’t survive review.

## Map search in six lines

2-char minimum · 300 ms debounce · one box for names/P-codes/coords ·
coordinate answers echo **exact** strings + admin chain + missing
levels + nearby · scope/type/level selects · *Search this area* is
antimeridian-safe.

## Confidence vocabulary

`confirmed > probable > possible > uncertain > disputed` (registry:
Authentication level). Downgrade honestly when Evidence contradicts.

## Commands you may need (server)

```bash
git -C ~/frappe-bench/apps/siraj_research pull
bench --site frappe.com migrate
bench build --app siraj_research        # only after JS changes
```

---

# المرجع السريع (صفحة واحدة)

## الخطوات العشر

| # | الخطوة | المخرج | المختصر |
|---|---|---|---|
| 1 | الإعدادات | لغة وأدوار وافتراضيات | `/app/siraj-settings` |
| 2 | المواقع | سجلات مكان؛ إحداثيات ← تسلسل | `/app/place` |
| 3 | المصادر | Source + تصنيف موثوقية | `/app/source` |
| 4 | الأفراد | أشخاص + أسرة + بوابة الحالة | `/app/person` |
| 5 | المؤسسات | مؤسسات ثنائية مصنّفة | `/app/institution` |
| 6 | الوحدات | وحدة باب وقائد | `/app/military-unit` |
| 7 | الأحداث | أحداث بصدق الدقة | `/app/siraj-event` |
| 8 | العلاقات | مُنمَّطة موجَّهة مسنَدة | `/app/relationship` |
| 9 | بيانات أخرى | وسوم وأدلة واستيراد وجودة | مساحة العمل + الإعدادات |
| 10 | البحث | قوائم + عام + خريطة + تسلسل | `/app/siraj-explorer` |

## التواريخ — ثلاثة حقول

`as_stated` (حرّي لا يُمسّ) + `comparable` (موحّد) + `precision`
(`exact … app`). لا تدّعِ `exact` لا تملكه.

## الإحداثيات — قواعد صارمة

**لا تقريب ولا اختصار أبدًا** · مدخل: `31.5, 34.47` أو درجات-دقيقة-
ثانية (تُقبل الأرقام العربية وش/ج/ق/غ) · ضَعها في **كتلة Geo** →
تعبئة تلقائية للفارغة فقط · المستويات غير المحددة تبقى فارغة
وتظهر في `missing_levels`.

## الحد الأدنى الإلزامي

Source: العنوان والنوع · Place: الاسم والنوع والمستوى · Institution:
الاسم العربي والنوع · Military unit: الاسم والطبقة والحالة · Event:
العنوان العربي والنوع · Relationship: النوع والموضوع والكائن.

## الإسناد لكل ادعاء

`primary_source` + `authentication_level` + صف **Evidence**.

## بحث الخريطة في ست سطور

حرفان كحدّ أدنى · إرجاء 300 مللي · مربع واحد للأسماء ورموز
والإحداثيات · ردّ الإحداثيات **دقة كاملة** + سسلة إدارية + ناقص
مُسمّى + أقرب · فلاتر النطاق/النوع/المستوى · *Search this area*
آمن خط التاريخ.

## مفردات الثقة

`confirmed > probable > possible > uncertain > disputed`. اخفضها بصدق
عندما ينقضك دليل.

## أوامر الخادم

```bash
git -C ~/frappe-bench/apps/siraj_research pull
bench --site frappe.com migrate
bench build --app siraj_research        # بعد تغيير JS فقط
```
