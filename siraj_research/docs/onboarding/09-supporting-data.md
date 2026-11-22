# Step 9 — Other essential data: tags, documents, attachments, import/export

**Goal.** Round out the registry: tags for cross-cutting themes,
documents/evidence for claims, attachments for scans — plus the
import/export machinery and the quality loop.

**Prerequisites.** Steps 1–8; workspace open.

---

## 9.1 Tags

Tags are Frappe’s built-in Tag applied to any record (person, event,
institution…). Use them for themes that cut across types:
`#disputed-date`, `#gaza-1948`, `#needs-translation`.

*Rules:* lowercase, hyphenated, no spaces; one tag per idea; prune
quarterly. Tags show in search and list filters — they are navigation,
not evidence (evidence lives in Evidence rows).

## 9.2 Documents, scans, attachments

Three layers, in order of authority:

1. **Source + Scan/PDF** (step 3) — the document itself, archived.
2. **Evidence child rows** on each record — the precise tie: *which
   source, supports/contradicts/contextualizes, which field, page or
   timestamp*.
3. **Image / attachment fields** on records (emblems, photos) — visual
   material with **alt text**.

*Common mistake:* uploading a scan to the record instead of to the
Source — the same PDF must be reachable from the claim it supports.

## 9.3 Import / export

Controlled by **SIRAJ Settings** (step 1):

| Knob | Meaning | Guidance |
|---|---|---|
| Maximum rows per import | Hard cap | Raise only with memory headroom |
| Default import mode | `Insert New Records` / `Update Existing Records` / `Insert or Update` | Match your ID column semantics; `Update` with mismatched ids silently inserts nothing |
| Maximum rows per export | Hard cap | — |
| Export Arabic vocabulary labels | Adds Arabic label columns | On for bilingual deliverables |

The import pipeline validates rows before writing; fix reported rows and
re-run — imports are idempotent in `Insert or Update` mode when ids
match.

## 9.4 Keep the data clean (the quality loop — in-app record: *Review data quality*)

- Run the **Review data quality** onboarding step / quality queue
  regularly: completeness, stale reviews (`stale_review_days` from step
  1), suspect claims.
- Every published claim should trace to a Source (enable *Require a
  source before publishing* once the team has sources).
- Re-check Authentication levels when new Evidence contradicts old.

## 9.5 Worked example

1. Tag five Gaza-related records `#gaza-1948`.
2. Attach the step-3 scan to the Source; add an Evidence row on the
   event: `supports`, field `start_date`, page `2`.
3. Export with **Export Arabic vocabulary labels** on; re-import the
   same file with mode `Insert or Update` — expect zero duplicates.

## Validation checkpoint

You should now see: tags filtering list views; the PDF reachable from
both Source and claim; an export containing Arabic label columns; a
re-import creating no duplicates; the quality queue shrinking after
review.

**Common mistakes:** tags as sentences; scan attached to the record
only; import mode mismatch; skipping the quality loop after the first
import.

**Next:** [Step 10 — Searching everything](10-searching.md)

---

# الخطوة 9 — البيانات الأساسية الأخرى: الوسوم، المستندات، المرفقات، الاستيراد/التصدير

**الهدف.** استكمال السجل: وسوم للموضوعات المشتركة، مستندات وأدلة
للادعاءات، مرفقات للمسوحات — مع آلية الاستيراد/التصدير وحلقة الجودة.

**المقدّمات.** الخطوات 1–8؛ مساحة العمل مفتوحة.

---

## 9.1 الوسوم

الوسوم (Tag) ميزة Frappe المدمجة تُطبَّق على أي سجل لثيمات تتقاطع
مع الأنواع: `#disputed-date`، `#gaza-1948`، `#needs-translation`.

**القواعد:** صغيرة، بشرطات، بلا مسافات؛ وسم واحد لكل فكرة؛ مراجعة
ربع سنوية. تظهر في البحث وفلاتر القوائم — هي تنقّل لا دليل (الدليل في
صفوف Evidence).

## 9.2 المستندات والمسوحات والمرفقات

ثلاث طبقات بحسب الصلاحية:

1. **Source + Scan/PDF** (خطوة 3) — الوثيقة نفسها المؤرشفة.
2. **صفوف Evidence** على كل سجل — الوصلة الدقيقة: *أي مصدر،
   يدعم/يناقض/يسياق، أي حقل، صفحة أو طابع زمني*.
3. حقول **Image/Attachment** على السجلات (شعارات، صور) بنص بديل.

**خطأ شائع:** رفع المسح إلى السجل لا إلى المصدر — يجب أن تكون
الPDF نفسها قابلة للوصول من الادعاء الذي تسنده.

## 9.3 الاستيراد/التصدير

تتحكم **SIRAJ Settings** (خطوة 1):

| المفتاح | المعنى | إرشاد |
|---|---|---|
| Maximum rows per import | سقف صارم | ارفعه فقط مع مساحة ذاكرة |
| Default mode | Insert / Update / Insert or Update | وافق مع دلالة عمود المعرّفات؛ `Update` بمعرّفات مختلقة لا يُدخل شيئًا |
| Maximum rows per export | سقف صارم | — |
| Export Arabic vocabulary labels | أعمدة تسميات عربية | مفعّل لتسليمات ثنائية |

خط الاستيراد يتحقق من الصفوف قبل الكتابة؛ صحّح المُبلَّغ عنها وأعد
التشغيل — الاستيراد idempotent في `Insert or Update` عند تطابق
المعرّفات.

## 9.4 حافظ على نظافة البيانات (حلقة الجودة — السجل: «مراجعة جودة البيانات»)

- شغّل *Review data quality* دوريًا: اكتمال، مراجعات قديمة
  (`stale_review_days`)، ادعاءات مشبوهة.
- كل ادعاء منشور يصل إلى Source (فعّل *Require a source before
  publishing* بعد توفر المصادر).
- راجع مستويات الثقة عند ورود Evidence متناقض.

## 9.5 مثال عملي

1. وسّم خمسة سجلات مرتبطة بغزة `#gaza-1948`.
2. أرفق مسح خطوة 3 بالمصدر؛ صف Evidence على الحدث: `supports`،
   الحقل `start_date`، الصفحة `2`.
3. صدّر مع **Export Arabic vocabulary labels**؛ أعد استيراد الملف
   نفسه بوضع `Insert or Update` — بلا تكرارات.

## نقطة التحقق

يجب أن ترى: الوسوم تفلتر قوائم السجلات؛ الـ PDF قابلًا من المصدر
والادعاء معًا؛ التصدير يحوي أعمدة التسميات العربية؛ إعادة الاستيراد
لا تكرر؛ طابور الجودة يتقلص بعد المراجعة.

**أخطاء شائعة:** وسوم كجمل؛ مسح مرفق على السجل فقط؛ عدم تطابق وضع
الاستيراد؛ إهمال حلقة الجودة بعد أول استيراد.

**التالي:** [الخطوة 10 — البحث في كل شيء](10-searching.md)
