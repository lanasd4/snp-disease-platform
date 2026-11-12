# 3.4 دراسة سهولة الاستخدام (للتوزيع)

**الهدف:** قياس مدى سهولة استخدام المنصة لدى مستخدمين عرب (طلاب علوم صحية، أطباء، باحثين)، بمقياس معياري ومهام محددة.

> **قبل البدء:** اسألي مشرفك أو الجامعة إن كانت الدراسة تحتاج موافقة لجنة أخلاقيات البحث (IRB). كثير من الجامعات تطلبها حتى للاستبيانات المجهولة.

## المشاركون
- **العدد:** 15 إلى 30 مشاركًا. العدد 15 كافٍ لتقدير SUS بشكل معقول، و30 أفضل لمقارنة المجموعات.
- **المجموعات** (عمود `group`): `student` أو `clinician` أو `researcher`.
- **البيانات:** لا تُجمع أسماء ولا بيانات تعريفية. استخدمي رقمًا لكل مشارك (P01، P02...).

## نص الموافقة (يُقرأ قبل البدء)
> هذه دراسة لتقييم سهولة استخدام منصة تعليمية عن الجينات والأمراض. ستنفذ خمس مهام قصيرة ثم تجيب عن عشرة أسئلة. المدة نحو 15 دقيقة. المشاركة تطوعية، ويمكنك التوقف في أي وقت، ولن تُجمع أي معلومات تعرّف بك. نحن نقيّم المنصة لا نقيّمك.

## المهام الخمس
لكل مهمة سجّلي: نجحت (1) أو لم تنجح (0)، والزمن بالثواني (`task_N` و`time_N`). لا تساعدي المشارك أثناء المهمة.

1. **ابحث عن مرض السكري،** وما الجين في المرتبة الأولى؟ (النجاح: يذكر جينًا من أول صف في الجدول.)
2. **ابحث عن المتغير الجيني rs429358،** ولأي مرض هو؟ (النجاح: الزهايمر.)
3. **افتح تفاصيل أي نتيجة،** ثم افتح الدراسة الأصلية على PubMed. (النجاح: يصل إلى صفحة PubMed.)
4. **اعرض النتائج المستمدة من عينات عربية فقط** لمرض قصور الغدة الدرقية. (النجاح: يفعّل خيار "النتائج العربية فقط" ويرى نتائج.)
5. **قارن مرض السمنة بسرطان الثدي** في صفحة الترتيب. (النجاح: يختار المرضين في قائمة المقارنة.)

## مقياس سهولة الاستخدام SUS (بعد المهام)
**الاستخدام:** عشرة بنود، يجيب المشارك عن كل بند من 1 (لا أوافق بشدة) إلى 5 (أوافق بشدة)، وتُسجّل الإجابات في الأعمدة `sus_1` إلى `sus_10` بنفس الترتيب.

**النسخة العربية:** استخدمي **النسخة العربية المحكّمة**:
> AlGhannam, B. A., Albustan, S. A., Al-Hassan, A. A., & Albustan, L. A. (2018). Towards a Standard Arabic System Usability Scale: Psychometric Evaluation using Communication Disorder App. *International Journal of Human-Computer Interaction, 34*(9), 799–804. https://doi.org/10.1080/10447318.2017.1388099

انسخي الصياغة العربية للبنود من الورقة نفسها، ولا تترجمي البنود بنفسك، لأن الترجمة غير المحكّمة تُضعف صلاحية النتائج.

**البنود الأصلية بالإنجليزية (Brooke, 1996)** للرجوع والمطابقة:
1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

## أسئلة إضافية (اختيارية، في عمود `comments`)
- ما أكثر شيء أعجبك؟
- ما أكثر شيء أربكك؟
- هل الشرح بالعربية مفهوم؟

## التحليل (أنا أشغّله بعد جمع البيانات)
1. انسخي `analysis/usability/responses_template.csv` إلى `analysis/usability/responses.csv` واملئيه، بصف لكل مشارك.
2. شغّلي:
   ```
   python -m analysis.usability
   ```
3. **الناتج** (`analysis/results/usability_summary.json`):
   - متوسط SUS مع فترة ثقة 95%، ونسبة المشاركين فوق المتوسط المرجعي 68؛
   - نسبة نجاح كل مهمة مع فترة ثقة (Wilson)، ووسيط الزمن؛
   - مقارنة متوسط SUS بين المجموعات.

**طريقة الحساب** (Brooke, 1996):
- البنود الفردية = الإجابة − 1؛
- البنود الزوجية = 5 − الإجابة؛
- المجموع × 2.5 = درجة من 0 إلى 100.

**المتوسط المرجعي:** 68، وهو المتوسط الشائع عبر الدراسات المنشورة حسب Sauro & Lewis.
