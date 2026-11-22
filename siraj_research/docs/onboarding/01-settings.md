# Step 1 — Settings: language, defaults, offline data, map data, roles

**Goal.** Configure the site once, before any data entry: interface
language, publishing/import defaults, offline map & boundary data, the
base map, and who may do what.

**Prerequisites.** You are signed in as **System Manager** or **SIRAJ
Administrator** (settings are Singles — only these roles can save them).
The SIRAJ workspace is open ([Before you begin](README.md#before-you-begin)).

---

## 1.1 Language (per user)

The app ships an Arabic translation (`ar.csv`); the interface language is
a per-user preference:

1. Click your avatar → **My Profile** (or `/app/user`).
2. Set **Language** to `Arabic` (العربية) for the Arabic interface, or
   keep `English`.
3. Save; the UI re-renders in the chosen language on next reload.

*Common mistake:* language is per user — changing yours does not change
it for colleagues. Each user sets their own.

## 1.2 SIRAJ Settings (`/app/siraj-settings`)

A Single DocType: instance-wide policy for the registry. All fields are
optional (the app ships defaults); nothing here is required to save.

| Field | Meaning | Format / range | Common mistakes |
|---|---|---|---|
| Require a source before publishing | Blocks publishing a record that has no linked Source | Checkbox | Turning it on before your team has any sources → nothing can be published. Set up sources (step 3) first or leave off while building. |
| Minimum completeness to publish (%) | Publish blocked below this completeness score | Integer 0–100 | Setting 100 → only perfect records publish. 70–80 is a sane start. |
| Days before a record is 'awaiting review' | Age after which records flow back to review | Integer, days | 0 disables the loop; very small values (e.g. 1) flood reviewers. |
| Maximum rows per import | Hard cap for one import file | Integer | Very large caps can exhaust memory on big files; the default is deliberate. |
| Default import mode | What import does with existing rows | `Insert New Records` / `Update Existing Records` / `Insert or Update` | `Update` on a file with different IDs creates nothing — check your ID column matches. |
| Maximum rows per export | Hard cap for one export | Integer | — |
| Export Arabic vocabulary labels | Adds Arabic label columns to exports | Checkbox | Off → exports carry English labels only. |
| Base map provider | Tiles the maps load by default | `local` / `osm` / `carto_*` / `esri_*` / … | `osm` needs outbound access; `local` serves cached tiles only (offline-first choice). |
| Initial latitude / longitude / zoom | The first view of every map | Decimal degrees, −90..90 / −180..180; zoom integer | **Coordinates are stored and displayed at full precision — never shorten or round them.** Type the exact values you mean. |
| Maximum markers per view | Caps drawn markers (performance) | Integer | Too low hides results on dense maps; too high slows old devices. |
| Group nearby markers | Clusters overlapping markers | Checkbox | Off → dense areas render thousands of pins. |
| Measurement units | Distances on the map | `metric` / `imperial` | — |
| Place labels on the map | Shows gazetteer labels | Checkbox | — |
| Default overlays | Comma-separated overlay ids | Small text | Unknown ids are ignored — copy ids from the map’s layer control. |
| Download zoom ceiling / size cap / politeness delay | Offline map-download limits (zoom, tiles, ms between requests) | Integers | Raising the delay is polite to tile providers; raising caps needs disk space. |

## 1.3 Geo Settings (`/app/geo-settings`)

Site-wide settings for administrative auto-fill, offline boundary &
gazetteer data, and the online fallback. Also a Single.

**Datasets (needed by step 2)**

| Field | Meaning | Format | Common mistakes |
|---|---|---|---|
| Active boundary dataset | Which Admin Boundary dataset region search & the cascade use | Link → Boundary Dataset | Left empty → region search has no polygons. Import a dataset first (step 2). |
| Active gazetteer dataset | Which Gazetteer Place dataset place search uses | Link → Boundary Dataset | Same as above. |
| Border tolerance (m) | Slack when deciding a point sits on a border | Integer metres | Too small → points metres from a border report “outside”; too large → wrong side of a border accepted. |

**Offline data & tiles**

| Field | Meaning | Format | Common mistakes |
|---|---|---|---|
| Default map layer | Layer shown first | `standard` / `aerial` / `hybrid` / `toner` / `terrain` / `watercolor` / `usgs_topo` | Layers whose “enable” checkbox is off will not appear. |
| Enable Standard (Aerial, Hybrid, Toner, Terrain, Watercolor, USGS Topo, NASA MODIS) | Which layers users may pick | Checkboxes | Disabling everything leaves the map blank. |
| Allow server to fetch from provider | Lets the server cache tiles for offline use | Checkbox | Off → no server-side tile cache; online-only maps. |
| Default tile layer + Cached tiles / Cache size (read-only) | Server tile cache state | Integers (read-only) | — |
| Tile cache TTL (days) | How long a cached tile stays valid | Integer | Very short → repeated fetches; very long → stale imagery. |
| Allow online setup downloads / Run Online Setup | One-shot download of offline boundary/gazetteer data | Checkbox + button | Needs internet; the run is idempotent and can be re-run after failures. |
| Stop Offline Bootstrap / Stop requested | Stops a running bootstrap | Button | Use only if a run is stuck; re-run afterwards. |

**Online fallback policy (hybrid, offline-first)**

| Field | Meaning | Format | Common mistakes |
|---|---|---|---|
| Enable online geocoder fallback | Allows Nominatim/Esri/Photon lookups when local data misses | Checkbox | Leave **off** for fully offline sites — local resolution still works. |
| Provider / API key / Rate limit (req/min) / Cache online results (days) | Who to call, how often, and how long to remember | Select / password / integer / integer | Exceeding provider limits gets you blocked; caching reduces calls. |
| Use online fallback when | `Missing country` / `Missing any level` / `Always` | Select | `Always` costs calls even when local data is complete. |
| Online User-Agent / Minimum seconds between online calls | Politeness identity and spacing | Text / integer | A real contact User-Agent is required by OSM’s usage policy. |
| Nearest-place max distance (m) / Ambiguity threshold (m) | Reverse-geocoding cutoffs | Integer metres | Huge distances attach a “nearest place” from the wrong region. |
| Sea/gap warning distance (km) | Warns when a point is this far from any known place | Integer km | — |

**Hierarchy auto-fill (used in steps 2–8)**

| Field | Meaning | Format | Common mistakes |
|---|---|---|---|
| Create missing hierarchy records | Saving a record with coordinates but a missing level creates that level locally | Checkbox | Off → coordinates save but the chain stays incomplete. Only local imported data is created — never invented names. |
| Use nearest gazetteer place as village | Links the nearest gazetteer place as the village level | Checkbox | On disputed/ambiguous points prefer manual review. |
| Default country code | Country assumed when a point resolves nowhere else | ISO code (e.g. `PS`) | Wrong default silently files points under the wrong country. |

## 1.4 Roles (per user)

Four roles ship with the app and are granted per user:

| Role | Typical use |
|---|---|
| SIRAJ Viewer | Read and search only |
| SIRAJ Researcher | Create and edit records, no delete |
| SIRAJ Reviewer | Review, publish, import/export |
| SIRAJ Administrator | Full control incl. delete and settings |

Assign them at **User → user → Roles** (or a Role Profile). *Common
mistake:* granting System Manager “just to see settings” — use SIRAJ
Administrator for day-to-day administration.

---

## Worked example

1. Avatar → My Profile → Language: `Arabic` → Save (skip if you prefer
   English).
2. `/app/siraj-settings` → set **Initial latitude** `31.5`,
   **Initial longitude** `34.47`, **Initial zoom** `11` (exact values —
   type them in full, never abbreviated), **Base map provider** `osm`,
   tick **Group nearby markers**, **Default import mode**
   `Insert or Update`.
3. `/app/geo-settings` → tick **Allow online setup downloads** →
   **Run Online Setup** (downloads boundary + gazetteer for offline use;
   idempotent — safe to re-run) → afterwards set **Active boundary
   dataset** and **Active gazetteer dataset** to the imported dataset →
   tick **Create missing hierarchy records** → **Use online fallback
   when**: `Missing country` → leave **Enable online geocoder fallback**
   off if the site must stay offline.
4. User → yourself → Roles: add `SIRAJ Researcher` → Save.

## Validation checkpoint

You should now see:

- **SIRAJ Settings** re-open showing your saved map centre
  `31.5 / 34.47` and zoom `11` (full precision, unchanged);
- **Geo Settings** showing the chosen **Active boundary dataset** and
  **Active gazetteer dataset**, with **Cached tiles** counting up after
  the online setup run;
- the Siraj Explorer map opening centred on your chosen point;
- your user card listing the **SIRAJ Researcher** role.

**Next:** [Step 2 — Locations: hierarchy and coordinate auto-fill](02-locations.md)

---

# الخطوة 1 — الإعدادات: اللغة، الافتراضيات، البيانات دون اتصال، بيانات الخريطة، الأدوار

**الهدف.** إعداد الموقع مرة واحدة قبل أي إدخال بيانات: لغة الواجهة،
افتراضيات النشر والاستيراد، بيانات الخريطة والحدود دون اتصال، خريطة
الأساس، ومن يملك أي صلاحية.

**المقدّمات.** تسجيل الدخول بصفة **System Manager** أو **SIRAJ
Administrator** (الإعدادات مستندات مفردة — هذان الوصفان فقط يحفظانها).
مساحة عمل السراج مفتوحة ([قبل أن تبدأ](README.md#قبل-أن-تبدأ)).

---

## 1.1 اللغة (لكل مستخدم)

يُشحن التطبيق ترجمة عربية (`ar.csv`)، ولغة الواجهة تفضيل خاص بكل مستخدم:

1. انقر صورتك → **ملفي الشخصي** (أو `/app/user`).
2. اضبط **Language** على `Arabic` للواجهة العربية، أو اترك `English`.
3. احفظ؛ تُعاد واجهة التطبيق باللغة المختارة عند إعادة التحميل.

**خطأ شائع:** اللغة خاصة بكل مستخدم — تغيير لغتك لا يغيّر لغة
زملائك؛ كل مستخدم يضبط لغته.

## 1.2 إعدادات السراج (`/app/siraj-settings`)

مستند مفرد: سياسة السجل على مستوى الموقع. جميع الحقول اختيارية
(التطبيق يشحن افتراضيات)؛ لا شيء إلزاميًا للحفظ.

| الحقل | المعنى | الصيغة/المدى | أخطاء شائعة |
|---|---|---|---|
| Require a source before publishing | يمنع نشر سجل بلا مصدر مرتبط | مربع اختيار | تفعيله قبل وجود مصادر → لا يُنشر شيء. جهّز المصادر (خطوة 3) أولًا أو اتركه مطفأًا أثناء البناء. |
| Minimum completeness to publish (%) | يمنع النشر دون هذا النسبة | عدد صحيح 0–100 | 100 يعني الكمال فقط؛ 70–80 بداية معقولة. |
| Days before a record is 'awaiting review' | عمر السجل قبل إعادته للمراجعة | عدد صحيح، أيام | 0 يوقف الحلقة؛ قيم صغيرة جدًا تغرق المراجعين. |
| Maximum rows per import | سقف صارم لملف استيراد واحد | عدد صحيح | سقوف ضخمة تستهلك الذاكرة؛ الافتراضي مقصود. |
| Default import mode | سلوك الاستيراد مع الصفوف الموجودة | `Insert New Records` / `Update Existing Records` / `Insert or Update` | `Update` بمعرّفات مختلفة لا ينشئ شيئًا — تأكد من تطابق عمود المعرّفات. |
| Maximum rows per export | سقف صارم لتصدير واحد | عدد صحيح | — |
| Export Arabic vocabulary labels | يضيف أعمدة تسميات عربية للتصدير | مربع اختيار | مطفأ → التصدير بالإنجليزية فقط. |
| Base map provider | بلاطات الخريطة الافتراضية | `local` / `osm` / `carto_*` / `esri_*` / … | `osm` يحتاج وصولًا خارجيًا؛ `local` من الكاش فقط (اختيار دون اتصال). |
| Initial latitude / longitude / zoom | أول عرض لكل خريطة | درجة عشرية، −90..90 / −180..180؛ تكبير عدد صحيح | **تُخزَّن الإحداثيات وتُعرض بدقّة كاملة — لا تقصّرها ولا تقرّبها أبدًا.** اكتب القيم كما تنويها تمامًا. |
| Maximum markers per view | سقف العلامات المرسومة (أداء) | عدد صحيح | منخفض جدًا يخفي نتائج المناطق الكثيفة؛ مرتفع جدًا يبطئ الأجهزة القديمة. |
| Group nearby markers | يجمّع العلامات المتداخلة | مربع اختيار | مطفأ → آلاف الدبابيس في المناطق الكثيفة. |
| Measurement units | المسافات على الخريطة | `metric` / `imperial` | — |
| Place labels on the map | يعرض تسميات دليل الجغرافيا | مربع اختيار | — |
| Default overlays | معرّفات طبقات مفصولة بفواصل | نص قصير | المعرّفات غير المعروفة تُتجاهل — انسخها من قائمة الطبقات. |
| Download zoom ceiling / size cap / politeness delay | حدود تنزيل الخريطة دون اتصال (تكبير، بلاطات، مللي ثانية بين الطلبات) | أعداد صحيحة | زيادة التأخير أكثر احترامًا لمزودي البلاطات؛ زيادة السقوف تحتاج مساحة قرص. |

## 1.3 إعدادات الجغرافيا (`/app/geo-settings`)

إعدادات الموقع للتعبئة التلقائية الإدارية وبيانات الحدود والدليل دون
اتصال وسياسة الاتصال الاحتياطي. هو أيضًا مستند مفرد.

**المجموعات (مطلوبة لخطوة 2)**

| الحقل | المعنى | الصيغة | أخطاء شائعة |
|---|---|---|---|
| Active boundary dataset | مجموعة حدود المنطقة التي يستخدمها البحث والتسلسل الهرمي | رابط → Boundary Dataset | فارغ → بلا مضلعات للبحث. استورد مجموعة أولًا (خطوة 2). |
| Active gazetteer dataset | مجموعة أماكن البحث | رابط → Boundary Dataset | كما أعلاه. |
| Border tolerance (m) | مرونة قرار «على الحدود» | أعداد صحيحة متر | صغيرة جدًا → نقاط قرب الحدود «خارج»؛ كبيرة جدًا → الجانب الخاطئ يُقبل. |

**البيانات دون اتصال والبلاطات**

| الحقل | المعنى | الصيغة | أخطاء شائعة |
|---|---|---|---|
| Default map layer | الطبقة الظاهرة أولًا | `standard` / `aerial` / `hybrid` / `toner` / `terrain` / `watercolor` / `usgs_topo` | الطبقات المُعطَّلة لا تظهر. |
| Enable Standard (Aerial، Hybrid، Toner، Terrain، Watercolor، USGS Topo، NASA MODIS) | الطبقات التي يجوز للمستخدمين اختيارها | مربعات اختيار | تعطيل الكل يُفرغ الخريطة. |
| Allow server to fetch from provider | يسمح للخادم تخزين البلاطات للاستخدام دون اتصال | مربع اختيار | مطفأ → بلا كاش خادم؛ خرائط عبر الإنترنت فقط. |
| Default tile layer + Cached tiles / Cache size (قراءة فقط) | حالة كاش البلاطات | أعداد (قراءة فقط) | — |
| Tile cache TTL (days) | عمر البلاط المخزّن | عدد صحيح | قصير جدًا → طلبات متكررة؛ طويل جدًا → صور قديمة. |
| Allow online setup downloads / Run Online Setup | تنزيل لمرة واحدة لبيانات الحدود والدليل | مربع + زر | يحتاج إنترنت؛ العملية idempotent وتعاد بعد الفشل. |
| Stop Offline Bootstrap / Stop requested | إيقاف تشغيل عالق | زر | فقط عند التعطّل؛ أعد التشغيل بعدها. |

**سياسة الاتصال الاحتياطي (هجين، دون اتصال أولًا)**

| الحقل | المعنى | الصيغة | أخطاء شائعة |
|---|---|---|---|
| Enable online geocoder fallback | يسمح ببحث Nominatim/Esri/Photon عند نقص البيانات المحلية | مربع اختيار | اتركه **مطفأً** للمواقع دون اتصال — التحديد المحلي يعمل. |
| Provider / API key / Rate limit / Cache online results | من نتصل وبكم وتذكير كم | Select / كلمة سر / عدد صحيح / عدد صحيح | تجاوز الحدود يحظرك؛ الكاش يقلل الطلبات. |
| Use online fallback when | `Missing country` / `Missing any level` / `Always` | Select | `Always` يستهلك طلبات مع اكتمال البيانات المحلية. |
| Online User-Agent / Minimum seconds between online calls | هوية اللباقة والتباعد | نص / عدد صحيح | يلزم User-Agent حقيقي حسب سياسة OSM. |
| Nearest-place max distance (m) / Ambiguity threshold (m) | حدود التحديد العكسي | عدد صحيح متر | مسافات ضخمة تربط «أقرب مكان» من منطقة خاطئة. |
| Sea/gap warning distance (km) | تحذير عندما تكون النقطة بعيدة عن أي مكان معروف | عدد صحيح كم | — |

**التعبئة التلقائية للتسلسل الهرمي (تُستخدم في الخطوات 2–8)**

| الحقل | المعنى | الصيغة | أخطاء شائعة |
|---|---|---|---|
| Create missing hierarchy records | حفظ سجل بإحداثيات ومستوى ناقص ينشئ المستوى محليًا | مربع اختيار | مطفأ → الإحداثيات تُحفظ والسلسلة تبقى ناقصة. تُنشأ البيانات المحلية المستوردة فقط — لا أسماء مُختلقة. |
| Use nearest gazetteer place as village | يربط أقرب مكان كمستوى قرية | مربع اختيار | في النقاط المتنازع عليها تفضّل المراجعة اليدوية. |
| Default country code | الدولة المفترضة حين لا يُحذّ شيء آخر | رمز ISO (مثل `PS`) | رمز خاطئ يُصنّف النقاط تحت دولة خاطئة بصمت. |

## 1.4 الأدوار (لكل مستخدم)

يُشحن التطبيق أربعة أدوار تُمنح لكل مستخدم:

| الدور | الاستخدام النموذجي |
|---|---|
| SIRAJ Viewer | قراءة وبحث فقط |
| SIRAJ Researcher | إنشاء وتحرير دون حذف |
| SIRAJ Reviewer | مراجعة ونشر واستيراد/تصدير |
| SIRAJ Administrator | تحكم كامل شامل الحذف والإعدادات |

تُمنح من **User → المستخدم → Roles** (أو Role Profile). **خطأ شائع:**
منح System Manager «لرؤية الإعدادات فقط» — استخدم SIRAJ Administrator
لإدارة اليوم اليوم.

---

## مثال عملي

1. الصورة → ملفي الشخصي → Language: `Arabic` → حفظ (تخطَّ إن فضلت
   الإنجليزية).
2. `/app/siraj-settings` → **Initial latitude** `31.5`، **Initial
   longitude** `34.47`، **Initial zoom** `11` (قيم كاملة — اكتبها كاملة
   دون اختصار)، **Base map provider** `osm`، فعّل **Group nearby
   markers**، **Default import mode** `Insert or Update`.
3. `/app/geo-settings` → فعّل **Allow online setup downloads** →
   **Run Online Setup** (ينزّل الحدود والدليل دون اتصال؛ آمن
   لإعادة التشغيل) → ثم اضبط **Active boundary dataset** و**Active
   gazetteer dataset** على المجموعة المستوردة → فعّل **Create missing
   hierarchy records** → **Use online fallback when**: `Missing country`
   → اترك **Enable online geocoder fallback** مطفأً إن كان الموقع دون
   اتصال.
4. User → أنت → Roles: أضف `SIRAJ Researcher` → حفظ.

## نقطة التحقق

يجب أن ترى الآن:

- **SIRAJ Settings** يعيد فتحه بمركز الخريطة المحفوظ `31.5 / 34.47`
  وتكبير `11` (دقة كاملة دون تغيير)؛
- **Geo Settings** يعرض **Active boundary dataset** و**Active
  gazetteer dataset** المختارتين، مع ارتفاع **Cached tiles** بعد تشغيل
  الإعداد؛
- خريطة مستكشف السراج تُفتح متمركزة على نقطتك؛
- بطاقة مستخدمك تعرض دور **SIRAJ Researcher**.

**التالي:** [الخطوة 2 — المواقع: التسلسل الهرمي والتعبئة التلقائية للإحداثيات](02-locations.md)
