
"""
PRS Prototype Engine
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
import math
import pandas as pd
from core.paths import get_project_root
from core.admin.common import get_active_ranked_path


def _clean_value(value: Any, default: str = "") -> str:
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    text = str(value).strip()

    if not text or text.lower() in ["nan", "none", "null", "na", "n/a"]:
        return default

    return text


def _to_float(value: Any, default: float = 0.0) -> float:
    text = _clean_value(value, "")

    if not text:
        return default

    try:
        return float(text)
    except Exception:
        return default


def _first_existing_col(df: pd.DataFrame, candidates: List[str]) -> str | None:
    lower_map = {str(c).lower(): c for c in df.columns}

    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]

    for c in candidates:
        c_lower = c.lower()
        for existing_lower, original in lower_map.items():
            if c_lower == existing_lower or c_lower in existing_lower or existing_lower in c_lower:
                return original

    return None


def load_active_ranked_results() -> pd.DataFrame:
    path = get_active_ranked_path()

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def get_available_diseases(df: pd.DataFrame | None = None) -> List[str]:
    if df is None:
        df = load_active_ranked_results()

    if df.empty:
        return []

    disease_col = _first_existing_col(df, ["disease_name", "disease", "trait"])

    if not disease_col:
        return []

    diseases = sorted(df[disease_col].dropna().astype(str).unique().tolist())

    return diseases


def filter_disease_associations(disease_name: str, max_snps: int = 10) -> pd.DataFrame:
    df = load_active_ranked_results()

    if df.empty:
        return df

    disease_col = _first_existing_col(df, ["disease_name", "disease", "trait"])

    if not disease_col:
        return pd.DataFrame()

    filtered = df[df[disease_col].astype(str).str.lower().eq(str(disease_name).lower())].copy()

    if filtered.empty:
        return filtered

    rsid_col = _first_existing_col(filtered, ["rsid", "rs_id", "snp", "snp_id"])
    score_col = _first_existing_col(filtered, ["importance_score", "score", "ranking_score"])

    if score_col:
        filtered[score_col] = pd.to_numeric(filtered[score_col], errors="coerce").fillna(0)
        filtered = filtered.sort_values(score_col, ascending=False)

    if rsid_col:
        filtered = filtered.drop_duplicates(subset=[rsid_col], keep="first")

    return filtered.head(max_snps).reset_index(drop=True)


def derive_prototype_weight(row: Dict[str, Any]) -> float:
    """Derive an educational prototype weight from available evidence fields."""
    effect_size = _to_float(row.get("effect_size", ""), default=0.0)

    if effect_size != 0:
        return round(effect_size, 4)

    odds_ratio = _to_float(row.get("odds_ratio", ""), default=0.0)

    if odds_ratio > 0:
        try:
            return round(math.log(odds_ratio), 4)
        except Exception:
            pass

    score = _to_float(row.get("importance_score", row.get("score", "")), default=0.0)

    if score > 0:
        return round(score / 100.0, 4)

    return 0.1


def normalize_prs_input_table(disease_name: str, max_snps: int = 10) -> pd.DataFrame:
    """Prepare a PRS input table for UI."""
    df = filter_disease_associations(disease_name, max_snps=max_snps)

    if df.empty:
        return pd.DataFrame(columns=[
            "rsid",
            "gene_symbol",
            "disease_name",
            "risk_allele",
            "p_value",
            "importance_score",
            "prototype_weight",
            "genotype_dosage",
        ])

    def get_value(row, candidates, default=""):
        lower_map = {str(k).lower(): k for k in row.index}

        for c in candidates:
            if c.lower() in lower_map:
                return row.get(lower_map[c.lower()], default)

        for c in candidates:
            c_lower = c.lower()
            for existing_lower, original in lower_map.items():
                if c_lower == existing_lower or c_lower in existing_lower or existing_lower in c_lower:
                    return row.get(original, default)

        return default

    rows = []

    for _, row in df.iterrows():

        normalized = {
            "rsid": _clean_value(get_value(row, ["rsid", "rs_id", "snp", "snp_id"]), "غير متوفر"),
            "gene_symbol": _clean_value(get_value(row, ["gene_symbol", "gene", "mapped_gene"]), "غير متوفر"),
            "disease_name": _clean_value(get_value(row, ["disease_name", "disease", "trait"]), disease_name),
            "risk_allele": _clean_value(get_value(row, ["risk_allele", "effect_allele"]), "غير متوفر"),
            "p_value": _clean_value(get_value(row, ["p_value", "p-value", "pvalue"]), "غير متوفر"),
            "importance_score": _clean_value(get_value(row, ["importance_score", "score", "ranking_score"]), "0"),
            "odds_ratio": _clean_value(get_value(row, ["odds_ratio", "or"]), ""),
            "effect_size": _clean_value(get_value(row, ["effect_size", "beta"]), ""),
        }

        normalized["prototype_weight"] = derive_prototype_weight(normalized)
        normalized["genotype_dosage"] = 0

        rows.append(normalized)

    return pd.DataFrame(rows)


def calculate_prs(input_df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate educational PRS prototype score."""
    if input_df is None or input_df.empty:
        return {
            "raw_score": 0.0,
            "normalized_score": 0.0,
            "risk_level": "غير متوفر",
            "risk_level_english": "Unavailable",
            "snp_count": 0,
            "details": pd.DataFrame(),
        }

    df = input_df.copy()

    df["prototype_weight"] = pd.to_numeric(df["prototype_weight"], errors="coerce").fillna(0.0)
    df["genotype_dosage"] = pd.to_numeric(df["genotype_dosage"], errors="coerce").fillna(0.0)

    df["genotype_dosage"] = df["genotype_dosage"].clip(lower=0, upper=2)
    df["prs_contribution"] = df["prototype_weight"] * df["genotype_dosage"]

    raw_score = round(float(df["prs_contribution"].sum()), 4)

    max_possible = float((df["prototype_weight"].abs() * 2).sum())

    if max_possible > 0:
        normalized_score = round((raw_score / max_possible) * 100, 2)
    else:
        normalized_score = 0.0

    if normalized_score < 33:
        risk_level = "منخفض تعليميًا"
        risk_level_english = "Low educational prototype level"
    elif normalized_score < 66:
        risk_level = "متوسط تعليميًا"
        risk_level_english = "Moderate educational prototype level"
    else:
        risk_level = "مرتفع تعليميًا"
        risk_level_english = "Higher educational prototype level"

    return {
        "raw_score": raw_score,
        "normalized_score": normalized_score,
        "risk_level": risk_level,
        "risk_level_english": risk_level_english,
        "snp_count": len(df),
        "details": df,
    }


def build_prs_interpretation(result: Dict[str, Any], disease_name: str) -> str:
    """Build Arabic interpretation for PRS prototype."""
    raw_score = result.get("raw_score", 0.0)
    normalized_score = result.get("normalized_score", 0.0)
    risk_level = result.get("risk_level", "غير متوفر")
    snp_count = result.get("snp_count", 0)

    text = f"""
### تفسير نموذج PRS التعليمي

تم حساب نموذج PRS أولي لمرض/صفة **{disease_name}** باستخدام **{snp_count}** من المتغيرات الجينية المتاحة داخل المنصة.

- **الدرجة الخام:** {raw_score}
- **الدرجة المعيارية التقريبية:** {normalized_score}%
- **المستوى التعليمي:** {risk_level}

### ماذا تعني هذه النتيجة؟

هذه النتيجة تمثل نموذجًا تعليميًا مبسطًا يوضح فكرة جمع مساهمات عدة SNPs في درجة واحدة. تم حساب المساهمة لكل SNP باستخدام عدد نسخ الأليل المدخل في المثال وضربه في وزن تقريبي مشتق من البيانات المتاحة داخل المنصة.

### حدود الاستخدام

هذا النموذج ليس PRS سريريًا معتمدًا، ولا يستخدم للتشخيص أو التنبؤ الطبي الحقيقي أو اتخاذ قرارات علاجية. الهدف منه توضيح الفكرة البحثية والتقنية لكيفية بناء PRS Prototype داخل منصة معلوماتية حيوية.
""".strip()

    return text


def export_prs_test(output_name: str = "prs_prototype_test.csv") -> Path:
    df = load_active_ranked_results()
    diseases = get_available_diseases(df)

    outputs_dir = get_project_root() / "outputs" / "tables"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    output_path = outputs_dir / output_name

    if not diseases:
        pd.DataFrame().to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path

    disease = diseases[0]
    input_df = normalize_prs_input_table(disease, max_snps=5)

    if not input_df.empty:
        input_df["genotype_dosage"] = [0, 1, 2, 1, 0][:len(input_df)]

    result = calculate_prs(input_df)

    details = result["details"].copy()

    if details.empty:
        details = input_df.copy()

    details["selected_disease"] = disease
    details["raw_score"] = result.get("raw_score", 0.0)
    details["normalized_score"] = result.get("normalized_score", 0.0)
    details["risk_level"] = result.get("risk_level", "")

    details.to_csv(output_path, index=False, encoding="utf-8-sig")

    return output_path


def validate_prs_input(input_df: pd.DataFrame) -> Dict[str, Any]:
    """Validate PRS input before calculation."""
    messages = []
    warnings = []
    errors = []

    if input_df is None or input_df.empty:
        errors.append("لا توجد SNPs متاحة لحساب نموذج PRS.")
        return {
            "is_valid": False,
            "messages": messages,
            "warnings": warnings,
            "errors": errors,
        }

    required_cols = ["rsid", "gene_symbol", "prototype_weight", "genotype_dosage"]

    for col in required_cols:
        if col not in input_df.columns:
            errors.append(f"العمود المطلوب غير موجود: {col}")

    if errors:
        return {
            "is_valid": False,
            "messages": messages,
            "warnings": warnings,
            "errors": errors,
        }

    df = input_df.copy()

    df["prototype_weight"] = pd.to_numeric(df["prototype_weight"], errors="coerce").fillna(0)
    df["genotype_dosage"] = pd.to_numeric(df["genotype_dosage"], errors="coerce")

    if df["genotype_dosage"].isna().any():
        errors.append("توجد قيم Genotype Dosage غير رقمية.")

    invalid_dosage = ~df["genotype_dosage"].isin([0, 1, 2])

    if invalid_dosage.any():
        errors.append("يجب أن تكون قيم Genotype Dosage فقط: 0 أو 1 أو 2.")

    if len(df) < 3:
        warnings.append("عدد SNPs قليل جدًا، لذلك النتيجة تعليمية ومحدودة جدًا.")

    if (df["prototype_weight"].abs().sum() == 0):
        warnings.append("كل الأوزان التقريبية تساوي صفر، لذلك لن تكون درجة PRS مفيدة.")

    missing_risk_allele = df["risk_allele"].astype(str).str.strip().isin(["", "غير متوفر", "nan", "None"]).sum() if "risk_allele" in df.columns else 0

    if missing_risk_allele > 0:
        warnings.append(f"يوجد {missing_risk_allele} SNP بدون risk allele واضح في البيانات.")

    if not errors:
        messages.append("مدخلات PRS صالحة للحساب التعليمي.")

    return {
        "is_valid": len(errors) == 0,
        "messages": messages,
        "warnings": warnings,
        "errors": errors,
    }


def build_prs_validation_report(input_df: pd.DataFrame, result: Dict[str, Any] | None = None) -> pd.DataFrame:
    """Build row-level PRS validation and contribution report."""
    if input_df is None or input_df.empty:
        return pd.DataFrame()

    df = input_df.copy()

    df["prototype_weight"] = pd.to_numeric(df["prototype_weight"], errors="coerce").fillna(0)
    df["genotype_dosage"] = pd.to_numeric(df["genotype_dosage"], errors="coerce").fillna(0)
    df["genotype_dosage"] = df["genotype_dosage"].clip(lower=0, upper=2)

    if "prs_contribution" not in df.columns:
        df["prs_contribution"] = df["prototype_weight"] * df["genotype_dosage"]

    df["validation_note"] = ""

    df.loc[df["prototype_weight"].eq(0), "validation_note"] += "وزن تقريبي صفر؛ "
    df.loc[df["genotype_dosage"].eq(0), "validation_note"] += "لا توجد نسخة من الأليل المؤثر؛ "
    df.loc[df["genotype_dosage"].eq(1), "validation_note"] += "نسخة واحدة من الأليل المؤثر؛ "
    df.loc[df["genotype_dosage"].eq(2), "validation_note"] += "نسختان من الأليل المؤثر؛ "

    return df

