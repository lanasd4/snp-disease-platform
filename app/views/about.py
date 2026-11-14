"""
About page: data sources, method, coverage and limitations.
"""

import json

import pandas as pd
import streamlit as st

from app.ui.components import feature_card, format_count, get_database_counts, page_header, section_title, stat_card
from core.diseases import list_diseases
from core.i18n import is_rtl, tr
from core.paths import RAW_DATA_DIR

SUBSET_METADATA = RAW_DATA_DIR / "gwas_catalog_platform_subset_metadata.json"


def _subset_metadata() -> dict:
    try:
        return json.loads(SUBSET_METADATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def render_about_page() -> None:
    page_header(
        tr("حول المنصة والمنهجية", "About & methodology"),
        subtitle=tr("من أين تأتي البيانات، كيف تُعالج وتُرتب، وما حدود استخدامها.",
                    "Where the data comes from, how it is processed and ranked, and its limits."),
        icon="ℹ️",
    )

    st.markdown(tr(
        "منصة معلوماتية حيوية تدعم اللغة العربية لاستكشاف الارتباطات بين المتغيرات الجينية (SNPs) والأمراض المزمنة، "
        "مع إبراز الأدلة المستمدة من عينات عربية وشرق أوسطية، وهي فئات ما زالت ممثلة بشكل محدود في دراسات الارتباط الجينومي.",
        "An Arabic-supported bioinformatics platform for exploring associations between genetic variants (SNPs) and "
        "chronic diseases, highlighting evidence from Arab and Middle Eastern samples, which remain under-represented "
        "in genome-wide association studies.",
    ))

    counts = get_database_counts()
    meta = _subset_metadata()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card(tr("الأمراض", "Diseases"), format_count(counts.get("Disease", 0)), icon="🩺")
    with c2:
        stat_card(tr("المتغيرات", "Variants"), format_count(counts.get("SNP", 0)), icon="🧬")
    with c3:
        stat_card(tr("الارتباطات", "Associations"), format_count(counts.get("Association", 0)), icon="🔗")
    with c4:
        stat_card(tr("الدراسات", "Studies"), format_count(counts.get("Study", 0)), icon="📚")

    section_title(tr("مصادر البيانات", "Data sources"))
    s1, s2, s3 = st.columns(3)
    with s1:
        feature_card("🧾", "GWAS Catalog", "كتالوج GWAS", tr(
            "قاعدة بيانات EBI/NHGRI للارتباطات الجينية المنشورة. نُسخة محلية من ملف الارتباطات الكامل"
            f" ({meta.get('catalog_file', '—')}).",
            f"EBI/NHGRI database of published genetic associations. Local copy of the full associations file"
            f" ({meta.get('catalog_file', '—')})."))
    with s2:
        feature_card("🧬", "dbSNP", "dbSNP", tr("معرّفات المتغيرات المرجعية (rsID) المستخدمة في كل الصفحات.",
                                                  "Reference variant identifiers (rsID) used throughout."))
    with s3:
        feature_card("📚", "PubMed", "PubMed", tr("معرّف المنشور لكل دراسة، مع رابط مباشر للمصدر الأصلي.",
                                                    "Publication id for every study, with a direct link to the source."))

    section_title(tr("المنهجية", "Method"))
    p_threshold = meta.get("p_value_threshold", 5e-8)
    st.markdown(tr(
        f"1. **الاختيار:** لكل مرض تُؤخذ السجلات التي صفتها المعيارية (EFO) تطابق المرض تمامًا، بمتغير واحد (rsID) "
        f"ودلالة على مستوى الجينوم (p < {p_threshold:g}).\n"
        f"2. **التوازن:** أقوى {meta.get('snps_per_disease', 150)} متغيرًا لكل مرض، مع حجز حتى "
        f"{meta.get('arab_reserved_snps', 30)} مقعدًا لمتغيرات مدعومة بعينات عربية/شرق أوسطية، وحتى "
        f"{meta.get('max_rows_per_snp', 5)} دراسات لكل متغير.\n"
        "3. **التنظيف والربط:** توحيد أسماء الأمراض والجينات، واستخراج المجموعات السكانية من وصف العينة، وإزالة التكرار.\n"
        "4. **مستوى الدليل:** «مؤكَّد» إذا بلغ الارتباط الدلالة على مستوى الجينوم في دراستين مستقلتين أو أكثر "
        "على كامل كتالوج GWAS، و«قوي» إذا بلغها في دراسة واحدة (التفاصيل في صفحة الترتيب).\n"
        "5. **إعادة الإنتاج:** كامل البيانات يُعاد بناؤه بأمر واحد: `python -m pipeline.rebuild_dataset`.",
        f"1. **Selection:** for each disease, records whose standard trait (EFO) matches the disease exactly, with a "
        f"single variant (rsID) and genome-wide significance (p < {p_threshold:g}).\n"
        f"2. **Balance:** the strongest {meta.get('snps_per_disease', 150)} variants per disease, reserving up to "
        f"{meta.get('arab_reserved_snps', 30)} slots for variants supported by Arab/Middle Eastern samples, and up to "
        f"{meta.get('max_rows_per_snp', 5)} studies per variant.\n"
        "3. **Cleaning and linking:** disease and gene names normalized, populations extracted from the sample "
        "description, duplicates removed.\n"
        "4. **Evidence level:** Confirmed when the association is genome-wide significant in two or more independent "
        "studies across the whole GWAS Catalog, Strong when in one study (see the Ranking page).\n"
        "5. **Reproducibility:** the whole dataset is rebuilt with one command: `python -m pipeline.rebuild_dataset`.",
    ))

    per_disease = pd.DataFrame(meta.get("per_disease", []))
    if not per_disease.empty:
        arabic = is_rtl()
        names = {d.name_en: f"{d.icon} {d.display_name(arabic)}" for d in list_diseases()}
        per_disease["disease"] = per_disease["disease"].map(lambda n: names.get(n, n))
        with st.expander(tr("تغطية البيانات لكل مرض", "Coverage per disease"), icon="📋"):
            st.dataframe(per_disease, hide_index=True, width="stretch", column_config={
                "disease": tr("المرض", "Disease"), "snps": tr("المتغيرات", "Variants"),
                "rows": tr("السجلات", "Records"), "arab_rows": tr("سجلات عربية/شرق أوسطية", "Arab/ME records"),
                "studies": tr("الدراسات", "Studies")})

    section_title(tr("حدود الاستخدام", "Limitations"))
    st.markdown(tr(
        "- المنصة أداة تعليمية وبحثية وليست أداة تشخيص أو تنبؤ بالخطر.\n"
        "- الارتباط الإحصائي لا يعني السببية، والمتغير المذكور قد يكون علامة قريبة من المتغير المسبب.\n"
        "- تمييز العينات العربية يعتمد على كلمات في وصف العينة، وقد يفوّت عينات غير موصوفة بوضوح.\n"
        "- البيانات عينة متوازنة من الكتالوج، وليست كل الارتباطات المنشورة.",
        "- The platform is for education and research; it is not a diagnostic or risk-prediction tool.\n"
        "- Statistical association is not causation; a reported variant may tag a nearby causal variant.\n"
        "- Arab-sample detection relies on keywords in the sample description and may miss unclear descriptions.\n"
        "- The data is a balanced subset of the catalog, not every published association.",
    ))

    section_title(tr("الخصوصية والسجلات", "Privacy and logs"))
    st.markdown(tr(
        "- البحث متاح بدون حساب، ولا نحفظ عمليات بحث الزوار.\n"
        "- عند تسجيل الدخول أو إنشاء حساب أو رفع محتوى، نسجّل اسم المستخدم والوقت وعنوان IP ونوع المتصفح "
        "في سجل عمليات لا يراه إلا الأدمن، لحماية الحسابات وتتبّع أي تغيير على البيانات العلمية.\n"
        "- لا نطلب الاسم الحقيقي أو البريد الإلكتروني، ولا نشارك هذه السجلات مع أي جهة.",
        "- Search works without an account, and visitors' searches are not stored.\n"
        "- When you sign in, create an account or submit content, we record the username, time, IP address and "
        "browser type in an audit log that only admins can see, to protect accounts and trace any change to the "
        "scientific data.\n"
        "- We do not ask for your real name or email, and we do not share these logs with anyone.",
    ))

    section_title(tr("فريق العمل", "Project team"))
    team = [
        ("👩‍💻", tr("إعداد وتطوير", "Design and development"),
         tr("المهندسة لانا سمان", "Eng. Lana Samman"), tr("جامعة قرطبة الخاصة", "Cordoba Private University")),
        ("🛠️", tr("الإشراف التقني (التقنيات والبرمجة)", "Technical supervision (technologies and code)"),
         tr("الدكتور كنان سمعان", "Dr. Kinan Samaan"), tr("جامعة قرطبة الخاصة", "Cordoba Private University")),
        ("🔬", tr("الإشراف العلمي (علم الأحياء وتدقيق المعلومات)", "Scientific supervision (biology and fact-checking)"),
         tr("الدكتور جوزيف شنكجي", "Dr. Joseph Shenekji"), tr("جامعة حلب", "University of Aleppo")),
    ]
    for col, (icon, role, name, place) in zip(st.columns(len(team)), team):
        with col:
            feature_card(icon, name, name, f"{role} · {place}")
