"""
Bilingual UI Infrastructure (Arabic / English)
"""

from __future__ import annotations

from typing import Dict
import streamlit as st


LANG_SESSION_KEY = "ui_lang"
DEFAULT_LANG = "ar"
SUPPORTED_LANGS = ("ar", "en")


# --------------------------------------------------------------------------- Translation dictionary  Keys...

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Navigation
    "nav.home": {"ar": "الرئيسية", "en": "Home"},
    "nav.search": {"ar": "البحث", "en": "Search"},
    "nav.ranking": {"ar": "التصنيف", "en": "Ranking"},
    "nav.ai_explanation": {"ar": "الشرح الذكي", "en": "AI Explanation"},
    "nav.study_summaries": {"ar": "ملخص الدراسات", "en": "Study Summaries"},
    "nav.circos": {"ar": "مخطط سيركوس", "en": "Circos Plot"},
    "nav.prs": {"ar": "نموذج PRS", "en": "PRS Prototype"},
    "nav.about": {"ar": "حول مصادر البيانات", "en": "About Data Source"},
    "nav.admin": {"ar": "لوحة الإدارة", "en": "Admin Dashboard"},

    # Common / shared across pages
    "common.login": {"ar": "تسجيل الدخول", "en": "Login"},
    "common.logout": {"ar": "تسجيل الخروج", "en": "Logout"},
    "common.account": {"ar": "الحساب", "en": "Account"},
    "common.username": {"ar": "اسم المستخدم", "en": "Username"},
    "common.password": {"ar": "كلمة المرور", "en": "Password"},
    "common.create_account": {"ar": "إنشاء حساب مستخدم", "en": "Create User Account"},
    "common.logged_in_as": {"ar": "مسجّل الدخول باسم", "en": "Logged in as"},
    "common.guest_user": {"ar": "مستخدم ضيف", "en": "Guest User"},
    "common.role": {"ar": "الدور", "en": "Role"},
    "common.search_button": {"ar": "بحث", "en": "Search"},
    "common.language": {"ar": "اللغة", "en": "Language"},
    "common.disclaimer_research_only": {
        "ar": "هذا المحتوى تعليمي وبحثي فقط، ولا يُستخدم للتشخيص أو اتخاذ قرارات علاجية.",
        "en": "This content is for education and research only - it is not for diagnosis or treatment decisions.",
    },

    # Home page
    "home.kicker": {"ar": "منصة ذكية مدعومة بالعربية", "en": "Smart Arabic-Supported"},
    "home.title": {"ar": "منصة SNP لعلم الأمراض الوراثي", "en": "SNP-Disease Bioinformatics Platform"},
    "home.subtitle": {
        "ar": "ربط التغيرات الجينية بالأمراض عبر اكتشاف ذكي، أدلة مرتبة، ورؤى تركّز على المنطقة العربية.",
        "en": "Bridging genomic variation and disease through intelligent discovery, ranked evidence, and Arab-focused insights.",
    },
    "home.diseases": {"ar": "الأمراض", "en": "Diseases"},
    "home.target_diseases": {"ar": "الأمراض المستهدفة", "en": "Target diseases"},
    "home.snps": {"ar": "تعددات النوكليوتيد", "en": "SNPs"},
    "home.loaded_variants": {"ar": "المتغيرات المحمّلة", "en": "Loaded variants"},
    "home.genes": {"ar": "الجينات", "en": "Genes"},
    "home.associated_genes": {"ar": "الجينات المرتبطة", "en": "Associated genes"},
    "home.studies": {"ar": "الدراسات", "en": "Studies"},
    "home.evidence_records": {"ar": "سجلات الأدلة", "en": "Evidence records"},
    "home.target_diseases_section": {"ar": "الأمراض المستهدفة", "en": "Target Diseases"},
    "home.platform_features": {"ar": "ميزات المنصة", "en": "Platform Features"},
    "home.view": {"ar": "عرض", "en": "View"},

    # Search page
    "search.title": {"ar": "البحث الذكي", "en": "Smart Search"},
    "search.subtitle": {
        "ar": "ابحث بالمرض أو المتغير الجيني أو الجين، واستعرض الارتباطات مرتبة حسب قوة الدليل العلمي.",
        "en": "Search by disease, genetic variant or gene and browse associations ranked by strength of evidence.",
    },
    "search.history": {"ar": "سجل البحث", "en": "Search History"},
    "search.type": {"ar": "نوع البحث", "en": "Search Type"},
    "search.by_gene": {"ar": "بحث الجين", "en": "Gene Search"},
    "search.by_snp": {"ar": "بحث SNP", "en": "SNP Search"},
    "search.by_disease": {"ar": "بحث الأمراض", "en": "Disease Search"},
    "search.disease_name": {"ar": "اسم المرض", "en": "Disease name"},
    "search.filters": {"ar": "فلاتر البحث", "en": "Search Filters"},
    "search.arab_only": {"ar": "النتائج العربية فقط", "en": "Arab-related results only"},
    "search.gene_symbol": {"ar": "رمز الجين", "en": "Gene symbol"},
    "search.snp_rsid": {"ar": "رقم SNP", "en": "SNP rsID"},
    "search.note_disease": {
        "ar": "ملاحظة: عند تجربة مرض جديد، اترك فلتر الجين فارغًا حتى لا يمنع ظهور النتائج.",
        "en": "Note: when trying a new disease, leave the Gene filter empty so it does not hide results.",
    },
    "search.note_gene": {
        "ar": "ملاحظة: في بحث الجين، اترك فلتر الجين فارغًا لأنه مستخدم كقيمة البحث الأساسية.",
        "en": "Note: in Gene search, leave the Gene filter empty - it is already used as the main search value.",
    },
    "search.note_snp": {
        "ar": "ملاحظة: اكتب rsID كاملًا للحصول على أدق نتيجة.",
        "en": "Note: type the full rsID for the most accurate result.",
    },
    "search.rank_label": {"ar": "درجة التصنيف", "en": "Rank Label"},
    "search.rank_very_high": {"ar": "مرتفع جدًا", "en": "Very High"},
    "search.rank_high": {"ar": "مرتفع", "en": "High"},
    "search.rank_moderate": {"ar": "متوسط", "en": "Moderate"},
    "search.rank_low": {"ar": "منخفض", "en": "Low"},
    "search.gene_label": {"ar": "الجين", "en": "Gene"},
    "search.gene_filter_locked": {
        "ar": "يتم استخدام رمز الجين الموجود في خانة البحث الأساسية",
        "en": "The gene symbol from the main search field is used",
    },
    "search.gene_filter_placeholder": {"ar": "اتركه فارغًا عند البحث العام", "en": "Leave empty for a general search"},
    "search.max_p_value": {"ar": "الحد الأعلى لقيمة p", "en": "Max p-value"},
    "search.sort_by": {"ar": "ترتيب حسب", "en": "Sort by"},
    "search.sort_importance": {"ar": "درجة الأهمية", "en": "Importance Score"},
    "search.sort_study_count": {"ar": "عدد الدراسات", "en": "Study Count"},
    "search.sort_gene_symbol": {"ar": "رمز الجين", "en": "Gene Symbol"},
    "search.min_score": {"ar": "الحد الأدنى للدرجة", "en": "Min Score"},
    "search.result_count": {"ar": "عدد النتائج", "en": "Number of results"},
    "search.top_score": {"ar": "أعلى درجة", "en": "Top Score"},
    "search.unique_snps": {"ar": "SNPs فريدة", "en": "Unique SNPs"},
    "search.genes_label": {"ar": "الجينات", "en": "Genes"},
    "search.displayed": {"ar": "المعروض", "en": "Displayed"},

    # About page
    "about.title": {"ar": "حول المنصة / مصادر البيانات", "en": "About / Data Sources"},
    "about.subtitle": {
        "ar": "نظرة عامة على نطاق المشروع ومصادر البيانات العلمية.",
        "en": "Overview of the project scope and scientific data sources.",
    },
    "about.body": {
        "ar": (
            "منصة معلوماتية حيوية ذكية تدعم اللغة العربية لربط تعددات النوكليوتيد "
            "بالأمراض، وتسهّل البحث والترتيب والشرح والتصوّر البصري."
        ),
        "en": (
            "The platform integrates genomic variation data with disease association "
            "evidence to support intelligent discovery, prioritization, explanation, "
            "a PRS prototype, and visual exploration."
        ),
    },
    "about.source_gwas": {"ar": "كتالوج GWAS", "en": "GWAS Catalog"},
    "about.source_gwas_text": {
        "ar": "دراسات الارتباط الجيني البشري المنسّقة.",
        "en": "Curated human genetic association studies.",
    },
    "about.source_dbsnp": {"ar": "قاعدة dbSNP", "en": "dbSNP / NCBI"},
    "about.source_dbsnp_text": {
        "ar": "معرّفات مجموعات SNP المرجعية.",
        "en": "Reference SNP cluster identifiers.",
    },
    "about.source_pubmed": {"ar": "بَبمِد", "en": "PubMed"},
    "about.source_pubmed_text": {
        "ar": "الأدبيات الطبية الحيوية ومعرّفات المنشورات.",
        "en": "Biomedical literature and publication identifiers.",
    },

    # Footer / misc chrome
    "footer.tagline": {
        "ar": "منصة SNP-Disease — نموذج بحثي حيوي معلوماتي مدعوم بالعربية",
        "en": "SNP-Disease Platform — Arabic-Supported Bioinformatics Research Prototype",
    },
    "common.admin_restricted": {
        "ar": "هذه الصفحة مخصصة للأدمن فقط.",
        "en": "This area is restricted to Admin users only.",
    },

    # Auth sidebar (core/auth.py) - shown on every page
    "auth.account": {"ar": "الحساب", "en": "Account"},
    "auth.logged_in_as": {"ar": "مسجّل الدخول باسم", "en": "Logged in as"},
    "auth.create_account": {"ar": "إنشاء حساب مستخدم", "en": "Create User Account"},
    "auth.new_username": {"ar": "اسم المستخدم الجديد", "en": "New username"},
    "auth.new_password": {"ar": "كلمة المرور الجديدة", "en": "New password"},
    "auth.confirm_password": {"ar": "تأكيد كلمة المرور", "en": "Confirm password"},
    "auth.register_self_note": {
        "ar": "التسجيل الذاتي ينشئ حساب مستخدم عادي فقط، ولا ينشئ حساب أدمن.",
        "en": "Self-registration creates a regular user account only - it never creates an admin.",
    },
    "auth.username_required": {"ar": "اسم المستخدم مطلوب.", "en": "Username is required."},
    "auth.password_min_length": {
        "ar": "كلمة المرور يجب أن تكون 8 أحرف على الأقل.",
        "en": "Password must be at least 8 characters.",
    },
    "auth.password_mismatch": {"ar": "كلمتا المرور غير متطابقتين.", "en": "Passwords do not match."},
    "auth.register_success": {
        "ar": "تم إنشاء الحساب وتسجيل الدخول بنجاح.",
        "en": "Account created and logged in successfully.",
    },
    "auth.register_failed_prefix": {"ar": "تعذر إنشاء الحساب", "en": "Could not create account"},
    "auth.login_success": {"ar": "تم تسجيل الدخول بنجاح.", "en": "Logged in successfully."},
    "auth.login_invalid": {
        "ar": "بيانات الدخول غير صحيحة أو الحساب غير نشط.",
        "en": "Invalid credentials or the account is inactive.",
    },
    "auth.login_locked_prefix": {
        "ar": "محاولات دخول فاشلة كثيرة لهذا الحساب. حاول مرة أخرى بعد قليل.",
        "en": "Too many failed login attempts for this account. Please try again shortly.",
    },
    "auth.role_admin_console": {"ar": "لوحة تحكم الأدمن", "en": "Admin Console"},
    "auth.role_research_user": {"ar": "مستخدم باحث", "en": "Research User"},
    "auth.explorer_plan": {"ar": "استكشاف مجاني", "en": "Explorer Plan"},
    "auth.role_label": {"ar": "الدور", "en": "Role"},
    "auth.must_change_password_warning": {
        "ar": "لا يمكن استخدام المنصة بكلمة المرور الافتراضية. يجب تعيين كلمة مرور جديدة لحساب الأدمن قبل الاستمرار.",
        "en": "The platform cannot be used with the default password. You must set a new password for this admin account before continuing.",
    },
    "auth.current_password": {"ar": "كلمة المرور الحالية", "en": "Current password"},
    "auth.new_password_min8": {"ar": "كلمة مرور جديدة (8 أحرف على الأقل)", "en": "New password (min 8 characters)"},
    "auth.confirm_new_password": {"ar": "تأكيد كلمة المرور الجديدة", "en": "Confirm new password"},
    "auth.change_password_button": {"ar": "تغيير كلمة المرور", "en": "Change Password"},
    "auth.new_password_mismatch": {"ar": "كلمتا المرور الجديدتان غير متطابقتين.", "en": "The new passwords do not match."},
    "auth.password_changed_success": {
        "ar": "تم تغيير كلمة المرور بنجاح. يمكنك الآن استخدام المنصة.",
        "en": "Password changed successfully. You can now use the platform.",
    },

    # Navigation chrome
    "nav.menu": {"ar": "القائمة", "en": "Menu"},

    # Home page (v2)
    "home.search_label": {"ar": "ابحث عن مرض أو متغير جيني أو جين", "en": "Search a disease, variant or gene"},
    "home.search_placeholder": {
        "ar": "مثال: السكري، الزهايمر، rs429358، APOE",
        "en": "e.g. Type 2 Diabetes, Alzheimer, rs429358, APOE",
    },
    "home.associations": {"ar": "الارتباطات", "en": "Associations"},
    "home.diseases_note": {"ar": "أمراض مزمنة ومعقدة", "en": "Chronic and complex diseases"},
    "home.snps_note": {"ar": "متغيرات جينية موثّقة", "en": "Documented genetic variants"},
    "home.associations_note": {"ar": "ارتباطات مرتبة حسب قوة الدليل", "en": "Ranked by strength of evidence"},
    "home.studies_note": {"ar": "دراسات من كتالوج GWAS", "en": "Studies from the GWAS Catalog"},
    "home.diseases_section": {"ar": "الأمراض المشمولة", "en": "Diseases covered"},
    "home.diseases_hint": {"ar": "اختر مرضًا لاستعراض متغيراته الجينية", "en": "Pick a disease to explore its variants"},
    "home.explore": {"ar": "استكشف", "en": "Explore"},
    "home.open": {"ar": "افتح ←", "en": "Open →"},
    "home.how_title": {"ar": "كيف تستخدم المنصة؟", "en": "How it works"},
    "home.step1": {"ar": "ابحث", "en": "Search"},
    "home.step1_text": {
        "ar": "اكتب اسم مرض بالعربية أو الإنجليزية، أو رقم متغير جيني (rsID)، أو رمز جين.",
        "en": "Type a disease name in Arabic or English, a variant ID (rsID) or a gene symbol.",
    },
    "home.step2": {"ar": "قارن الأدلة", "en": "Compare the evidence"},
    "home.step2_text": {
        "ar": "تظهر النتائج مرتبة حسب درجة الأهمية المبنية على قوة الدلالة الإحصائية وعدد الدراسات.",
        "en": "Results are ranked by an importance score built on statistical strength and study count.",
    },
    "home.step3": {"ar": "افهم النتيجة", "en": "Understand the result"},
    "home.step3_text": {
        "ar": "افتح أي نتيجة لترى شرحًا مبسطًا، والمصطلحات، وملخص الدراسة الأصلية.",
        "en": "Open any result for a plain-language explanation, key terms and a study summary.",
    },
    "home.features_title": {"ar": "أدوات المنصة", "en": "Platform tools"},
    "home.f_search": {"ar": "البحث الذكي", "en": "Smart search"},
    "home.f_search_text": {
        "ar": "بحث ثلاثي بالمرض أو المتغير أو الجين، يفهم المرادفات العربية والأخطاء الإملائية.",
        "en": "Search by disease, variant or gene, with Arabic synonyms and typo tolerance.",
    },
    "home.f_ranking": {"ar": "ترتيب الارتباطات", "en": "Association ranking"},
    "home.f_ranking_text": {
        "ar": "ترتيب الارتباطات حسب قوة الدليل: قيمة p، عدد الدراسات، والسياق السكاني.",
        "en": "Associations ranked by evidence: p-value, number of studies and population context.",
    },
    "home.f_arab": {"ar": "دراسات المنطقة العربية", "en": "Arab-region studies"},
    "home.f_arab_text": {
        "ar": "تمييز النتائج المستمدة من عينات عربية أو شرق أوسطية وتصفيتها بنقرة.",
        "en": "Results from Arab or Middle Eastern samples are flagged and can be filtered in one click.",
    },
    "home.f_ai": {"ar": "الشرح الذكي", "en": "AI explanation"},
    "home.f_ai_text": {
        "ar": "شرح عربي مبسط للمفاهيم مثل SNP وقيمة p ونسبة الأرجحية.",
        "en": "Plain-language explanations of concepts such as SNP, p-value and odds ratio.",
    },
    "home.f_summary": {"ar": "ملخص الدراسات", "en": "Study summaries"},
    "home.f_summary_text": {
        "ar": "ملخص منظم للدراسة التي تقف خلف كل ارتباط.",
        "en": "A structured summary of the study behind each association.",
    },
    "home.f_circos": {"ar": "مخطط العلاقات", "en": "Relationship map"},
    "home.f_circos_text": {
        "ar": "مخطط دائري تفاعلي يربط الأمراض بالجينات والمتغيرات.",
        "en": "Interactive circular map linking diseases, genes and variants.",
    },
    "home.f_prs": {"ar": "نموذج المخاطر الجينية", "en": "Polygenic risk demo"},
    "home.f_prs_text": {
        "ar": "نموذج تعليمي يوضح فكرة درجة المخاطر متعددة الجينات (PRS).",
        "en": "An educational demo of the polygenic risk score (PRS) idea.",
    },
    "home.f_sources": {"ar": "مصادر البيانات", "en": "Data sources"},
    "home.f_sources_text": {
        "ar": "البيانات مستخرجة من كتالوج GWAS ومرتبطة بمعرّفات dbSNP وPubMed.",
        "en": "Data comes from the GWAS Catalog, linked to dbSNP and PubMed identifiers.",
    },

    # Search page (v2)
    "search.mode_disease": {"ar": "مرض", "en": "Disease"},
    "search.mode_snp": {"ar": "متغير جيني (SNP)", "en": "Variant (SNP)"},
    "search.mode_gene": {"ar": "جين", "en": "Gene"},
    "search.input_disease": {"ar": "اسم المرض", "en": "Disease name"},
    "search.input_snp": {"ar": "رقم المتغير (rsID)", "en": "Variant ID (rsID)"},
    "search.input_gene": {"ar": "رمز الجين", "en": "Gene symbol"},
    "search.placeholder_disease": {"ar": "مثال: السكري، الربو، Breast Cancer", "en": "e.g. Asthma, السكري, Breast Cancer"},
    "search.placeholder_snp": {"ar": "مثال: rs429358", "en": "e.g. rs429358"},
    "search.placeholder_gene": {"ar": "مثال: APOE", "en": "e.g. APOE"},
    "search.quick_picks": {"ar": "اختيار سريع", "en": "Quick picks"},
    "search.advanced": {"ar": "خيارات متقدمة وتصفية", "en": "Advanced options and filters"},
    "search.sort_score": {"ar": "درجة الأهمية", "en": "Importance score"},
    "search.sort_pvalue": {"ar": "قيمة p (الأقوى أولًا)", "en": "p-value (strongest first)"},
    "search.sort_studies": {"ar": "عدد الدراسات", "en": "Number of studies"},
    "search.sort_gene": {"ar": "رمز الجين", "en": "Gene symbol"},
    "search.found": {"ar": "تم العثور على", "en": "Found"},
    "search.results_for": {"ar": "ارتباطًا لـ", "en": "associations for"},
    "search.showing_top": {"ar": "يُعرض أعلى {n} نتيجة. غيّر العدد من الخيارات المتقدمة.", "en": "Showing the top {n}. Change this in the advanced options."},
    "search.col_gene": {"ar": "الجين", "en": "Gene"},
    "search.col_disease": {"ar": "المرض", "en": "Disease"},
    "search.col_score": {"ar": "درجة الأهمية", "en": "Score"},
    "search.col_rank": {"ar": "قوة الارتباط", "en": "Strength"},
    "search.col_p": {"ar": "قيمة p", "en": "p-value"},
    "search.col_studies": {"ar": "الدراسات", "en": "Studies"},
    "search.col_arab": {"ar": "عربي", "en": "Arab"},
    "search.download": {"ar": "تحميل النتائج (CSV)", "en": "Download results (CSV)"},
    "search.details_title": {"ar": "تفاصيل النتيجة المختارة", "en": "Selected result"},
    "search.arab_badge": {"ar": "عينة عربية / شرق أوسطية", "en": "Arab / Middle East sample"},
    "search.risk_allele": {"ar": "الأليل المؤثر", "en": "Risk allele"},
    "search.odds_ratio": {"ar": "نسبة الأرجحية / Beta", "en": "Odds ratio / Beta"},
    "search.why_this_score": {"ar": "لماذا هذه الدرجة؟", "en": "Why this score?"},
    "search.tab_reason": {"ar": "سبب الترتيب", "en": "Ranking reason"},
    "search.tab_terms": {"ar": "المصطلحات", "en": "Key terms"},
    "search.tab_ai": {"ar": "الشرح الذكي", "en": "AI explanation"},
    "search.tab_study": {"ar": "ملخص الدراسة", "en": "Study summary"},
    "search.open_study_page": {"ar": "صفحة ملخص الدراسة", "en": "Study summary page"},
    "search.open_ai_page": {"ar": "صفحة الشرح الذكي", "en": "AI explanation page"},
    "search.open_pubmed": {"ar": "فتح الدراسة على PubMed", "en": "Open on PubMed"},
    "search.start_title": {"ar": "ابدأ بالبحث", "en": "Start searching"},
    "search.start_text": {
        "ar": "اكتب اسم مرض أو رقم متغير أو رمز جين، أو اختر من الاقتراحات أعلاه.",
        "en": "Type a disease, a variant ID or a gene symbol, or pick one of the suggestions above.",
    },
    "search.none": {"ar": "لا توجد نتائج", "en": "No results"},
    "search.none_hint_disease": {
        "ar": "تأكد من اسم المرض، أو اختر أحد الأمراض المشمولة من الاقتراحات.",
        "en": "Check the disease name, or pick one of the covered diseases above.",
    },
    "search.none_hint_snp": {"ar": "اكتب رقم المتغير كاملًا بصيغة مثل rs429358.", "en": "Type the full variant ID, e.g. rs429358."},
    "search.none_hint_gene": {"ar": "اكتب رمز الجين بالإنجليزية مثل APOE أو TCF7L2.", "en": "Type the gene symbol, e.g. APOE or TCF7L2."},
    "search.none_filtered": {"ar": "الفلاتر الحالية أخفت كل النتائج", "en": "The current filters hide every result"},
    "search.none_filtered_hint": {
        "ar": "خفّف الفلاتر من الخيارات المتقدمة (درجة الأهمية، قيمة p، قوة الارتباط).",
        "en": "Relax the filters in the advanced options (score, p-value, strength).",
    },
    "search.none_arab": {"ar": "لا توجد نتائج من عينات عربية لهذا البحث", "en": "No Arab-sample results for this search"},
    "search.none_arab_hint": {
        "ar": "أوقف خيار «النتائج العربية فقط» لعرض كل النتائج.",
        "en": "Turn off “Arab-related results only” to see every result.",
    },
    "search.history_empty": {"ar": "لا يوجد سجل بحث بعد.", "en": "No searches yet."},
    "search.history_clear": {"ar": "حذف سجل البحث", "en": "Clear search history"},
}


def get_lang() -> str:
    return st.session_state.get(LANG_SESSION_KEY, DEFAULT_LANG)


def set_lang(lang: str) -> None:
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    st.session_state[LANG_SESSION_KEY] = lang


def is_rtl() -> bool:
    return get_lang() == "ar"


def t(key: str, default: str | None = None) -> str:
    """Translate `key` into the active language; fall back to `default` or the key itself."""
    entry = TRANSLATIONS.get(key)

    if not entry:
        return default if default is not None else key

    lang = get_lang()

    return entry.get(lang) or entry.get(DEFAULT_LANG) or (default if default is not None else key)


def render_language_switch(location=st.sidebar) -> None:
    """Render a compact AR/EN toggle. Call once per page, typically in the sidebar."""
    current = get_lang()

    location.markdown(
        f"<div class='lang-switch-label'>{t('common.language')}</div>",
        unsafe_allow_html=True,
    )

    choice = location.radio(
        "language_switch",
        options=["ar", "en"],
        index=0 if current == "ar" else 1,
        format_func=lambda code: "العربية" if code == "ar" else "English",
        horizontal=True,
        label_visibility="collapsed",
        key="lang_switch_radio",
    )

    if choice != current:
        set_lang(choice)
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()


def inject_direction_css() -> None:
    """Flip the app's reading direction to match the active language."""
    direction = "rtl" if is_rtl() else "ltr"

    # styles.css uses logical properties (text-align: start, inline-start
    # borders), so setting the direction is enough to mirror the layout.
    st.markdown(
        f"""
        <style>
        .stApp, section[data-testid="stSidebar"] {{ direction: {direction}; }}
        .stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
        .stApp [data-testid="stMarkdownContainer"] {{ text-align: start; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def tr(arabic: str, english: str) -> str:
    """Inline bilingual text for one-off labels: returns the active language's version."""
    return arabic if is_rtl() else english
