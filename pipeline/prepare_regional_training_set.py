"""
Prepare Regional Training Set for Arab/Middle East ML Classifier
"""

from datetime import datetime
import json
import re
import pandas as pd
from core.paths import get_project_root


INPUT_FILENAME = "regional_tagged_associations.csv"
OUTPUT_FILENAME = "regional_training_set.csv"
METADATA_FILENAME = "regional_training_set_metadata.json"

TARGET_MIN_RECORDS = 80
TARGET_MAX_RECORDS = 150
RANDOM_SEED = 42


def get_paths() -> dict:
    """Return important project paths."""
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
        "docs": project_root / "docs",
    }


def ensure_directories() -> dict:
    """Create required directories."""
    paths = get_paths()

    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)
    paths["docs"].mkdir(parents=True, exist_ok=True)

    return paths


def clean_text(value):
    """Clean text and convert empty-like values to None."""
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def normalize_text(value) -> str:
    """Normalize Arabic and English text for ML input consistency."""
    text = clean_text(value)

    if text is None:
        return ""

    text = text.lower()

    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
    text = " ".join(text.split())

    return text


def choose_text_for_training(row: pd.Series) -> str:
    """Choose the best available text for classifier training."""
    preferred_fields = [
        "classification_text_used",
        "population_label",
        "region",
        "ancestry",
        "country",
        "study_title",
        "journal"
    ]

    parts = []

    for field in preferred_fields:
        if field in row.index:
            value = clean_text(row.get(field))
            if value:
                parts.append(value)

    if parts:
        return " | ".join(parts)

    return "No regional text available"


def map_rule_to_training_label(row: pd.Series) -> dict:
    """Labels:"""
    region_tag = clean_text(row.get("region_tag_rule")) or "Unknown"
    confidence = clean_text(row.get("rule_confidence")) or "Low"

    if region_tag in ["Arab/Middle East", "Middle East - Non-Arab/Regional"]:
        return {
            "suggested_label": "Arab_Middle_East",
            "final_label": "Arab_Middle_East",
            "label_confidence": confidence,
            "needs_manual_review": "N" if confidence in ["High", "Medium"] else "Y",
            "labeling_reason": "Mapped from rule-based Arab/Middle East regional tag."
        }

    if region_tag == "Other":
        return {
            "suggested_label": "Other",
            "final_label": "Other",
            "label_confidence": confidence,
            "needs_manual_review": "N" if confidence == "High" else "Y",
            "labeling_reason": "Mapped from rule-based Other regional tag."
        }

    return {
        "suggested_label": "Unknown_Review",
        "final_label": "Unknown_Review",
        "label_confidence": "Low",
        "needs_manual_review": "Y",
        "labeling_reason": "Unknown or no regional rule matched; requires manual review."
    }


def build_real_records_training_df(input_df: pd.DataFrame) -> pd.DataFrame:
    """Build labeled training candidate rows from real association records."""
    rows = []

    for index, row in input_df.iterrows():
        label_info = map_rule_to_training_label(row)
        classification_text = choose_text_for_training(row)

        rows.append({
            "record_source": "real_association",
            "source_row_number": index + 1,
            "source_record_id": clean_text(row.get("ranked_association_id")) or clean_text(row.get("ranking_feature_id")) or f"row_{index+1}",
            "classification_text": classification_text,
            "normalized_classification_text": normalize_text(classification_text),
            "suggested_label": label_info["suggested_label"],
            "final_label": label_info["final_label"],
            "label_confidence": label_info["label_confidence"],
            "needs_manual_review": label_info["needs_manual_review"],
            "labeling_reason": label_info["labeling_reason"],
            "rule_region_tag": clean_text(row.get("region_tag_rule")),
            "rule_subtag": clean_text(row.get("region_subtag_rule")),
            "matched_region_keywords": clean_text(row.get("matched_region_keywords")),
            "disease_name": clean_text(row.get("disease_name")),
            "rsid": clean_text(row.get("rsid")),
            "gene_symbol": clean_text(row.get("gene_symbol")),
            "population_label": clean_text(row.get("population_label")),
            "region": clean_text(row.get("region")),
            "ancestry": clean_text(row.get("ancestry")),
            "study_title": clean_text(row.get("study_title")),
        })

    df = pd.DataFrame(rows)
    df = df[df["normalized_classification_text"] != ""].copy()

    return df


def curated_seed_examples() -> pd.DataFrame:
    """Curated examples to support ML training when real data lacks Arab/Middle East records."""
    examples = [
        # Arab / Middle East examples
        ("Qatari population with type 2 diabetes", "Arab_Middle_East"),
        ("Saudi Arabian cohort study", "Arab_Middle_East"),
        ("Middle Eastern ancestry participants", "Arab_Middle_East"),
        ("Palestinian families from the West Bank", "Arab_Middle_East"),
        ("Jordanian population sample", "Arab_Middle_East"),
        ("Lebanese ancestry cohort", "Arab_Middle_East"),
        ("Syrian participants", "Arab_Middle_East"),
        ("Iraqi population group", "Arab_Middle_East"),
        ("Egyptian cohort study", "Arab_Middle_East"),
        ("Kuwaiti families", "Arab_Middle_East"),
        ("United Arab Emirates participants", "Arab_Middle_East"),
        ("Emirati cohort", "Arab_Middle_East"),
        ("Omani sample", "Arab_Middle_East"),
        ("Bahraini participants", "Arab_Middle_East"),
        ("Yemeni population", "Arab_Middle_East"),
        ("North African Arab population", "Arab_Middle_East"),
        ("Moroccan cohort", "Arab_Middle_East"),
        ("Tunisian population", "Arab_Middle_East"),
        ("Algerian sample", "Arab_Middle_East"),
        ("Libyan participants", "Arab_Middle_East"),
        ("Sudanese cohort", "Arab_Middle_East"),
        ("Levantine ancestry", "Arab_Middle_East"),
        ("Gulf Arab population", "Arab_Middle_East"),
        ("MENA ancestry group", "Arab_Middle_East"),
        ("دراسة على عينة سعودية", "Arab_Middle_East"),
        ("مرضى من فلسطين والاردن", "Arab_Middle_East"),
        ("عينة من الشرق الاوسط", "Arab_Middle_East"),
        ("مجموعة من الخليج العربي", "Arab_Middle_East"),
        ("مشاركون قطريون", "Arab_Middle_East"),
        ("عائلات فلسطينية", "Arab_Middle_East"),

        # Other examples
        ("European ancestry sample", "Other"),
        ("White British participants", "Other"),
        ("Finnish cohort", "Other"),
        ("East Asian population", "Other"),
        ("Han Chinese participants", "Other"),
        ("Japanese cohort", "Other"),
        ("Korean population", "Other"),
        ("South Asian participants", "Other"),
        ("Indian cohort", "Other"),
        ("Pakistani sample", "Other"),
        ("Bangladeshi population", "Other"),
        ("African American participants", "Other"),
        ("Sub-Saharan African cohort", "Other"),
        ("Nigerian sample", "Other"),
        ("Kenyan population", "Other"),
        ("Hispanic participants", "Other"),
        ("Latino cohort", "Other"),
        ("Mexican population", "Other"),
        ("Brazilian sample", "Other"),
        ("Latin American cohort", "Other"),
        ("سكان اوروبيون", "Other"),
        ("عينة صينية", "Other"),
        ("مجموعة يابانية", "Other"),
        ("مشاركون من كوريا", "Other"),
        ("دراسة على سكان من الهند", "Other"),

        # Unknown / review examples
        ("Unknown population", "Unknown_Review"),
        ("Population not reported", "Unknown_Review"),
        ("Not available ancestry information", "Unknown_Review"),
        ("Mixed population without country details", "Unknown_Review"),
        ("No regional text available", "Unknown_Review"),
        ("غير معروف", "Unknown_Review"),
        ("لم يتم تحديد المنطقة", "Unknown_Review"),
    ]

    rows = []

    for index, (text, label) in enumerate(examples, start=1):
        rows.append({
            "record_source": "curated_seed_example",
            "source_row_number": index,
            "source_record_id": f"CURATED_SEED_{index:04d}",
            "classification_text": text,
            "normalized_classification_text": normalize_text(text),
            "suggested_label": label,
            "final_label": label,
            "label_confidence": "High" if label != "Unknown_Review" else "Low",
            "needs_manual_review": "N" if label != "Unknown_Review" else "Y",
            "labeling_reason": "Curated regional text example for ML classifier training.",
            "rule_region_tag": None,
            "rule_subtag": None,
            "matched_region_keywords": None,
            "disease_name": None,
            "rsid": None,
            "gene_symbol": None,
            "population_label": None,
            "region": None,
            "ancestry": None,
            "study_title": None,
        })

    return pd.DataFrame(rows)


def sample_training_set(real_df: pd.DataFrame, seed_df: pd.DataFrame) -> pd.DataFrame:
    """Select a balanced-ish training set between 80 and 150 rows."""
    selected_parts = []

    target_by_label = {
        "Arab_Middle_East": 45,
        "Other": 45,
        "Unknown_Review": 20
    }

    for label, target_count in target_by_label.items():
        real_label_df = real_df[real_df["final_label"] == label].copy()

        if len(real_label_df) > target_count:
            real_sample = real_label_df.sample(
                n=target_count,
                random_state=RANDOM_SEED
            )
        else:
            real_sample = real_label_df

        selected_parts.append(real_sample)

        remaining = target_count - len(real_sample)

        if remaining > 0:
            seed_label_df = seed_df[seed_df["final_label"] == label].copy()

            if not seed_label_df.empty:
                seed_sample = seed_label_df.sample(
                    n=min(remaining, len(seed_label_df)),
                    random_state=RANDOM_SEED
                )
                selected_parts.append(seed_sample)

    combined_df = pd.concat(selected_parts, ignore_index=True)

    if len(combined_df) < TARGET_MIN_RECORDS:
        remaining_seed = seed_df[
            ~seed_df["source_record_id"].isin(combined_df["source_record_id"])
        ].copy()

        needed = TARGET_MIN_RECORDS - len(combined_df)

        if not remaining_seed.empty:
            extra_seed = remaining_seed.sample(
                n=min(needed, len(remaining_seed)),
                random_state=RANDOM_SEED
            )
            combined_df = pd.concat([combined_df, extra_seed], ignore_index=True)

    if len(combined_df) > TARGET_MAX_RECORDS:
        combined_df = combined_df.sample(
            n=TARGET_MAX_RECORDS,
            random_state=RANDOM_SEED
        ).reset_index(drop=True)

    combined_df = combined_df.drop_duplicates(
        subset=["normalized_classification_text", "final_label"],
        keep="first"
    ).reset_index(drop=True)

    combined_df["training_record_id"] = [
        f"REGTRAIN_{index:05d}"
        for index in range(1, len(combined_df) + 1)
    ]

    output_columns = [
        "training_record_id",
        "record_source",
        "source_record_id",
        "source_row_number",
        "classification_text",
        "normalized_classification_text",
        "suggested_label",
        "final_label",
        "label_confidence",
        "needs_manual_review",
        "labeling_reason",
        "rule_region_tag",
        "rule_subtag",
        "matched_region_keywords",
        "disease_name",
        "rsid",
        "gene_symbol",
        "population_label",
        "region",
        "ancestry",
        "study_title"
    ]

    return combined_df[output_columns].copy()


def create_balance_report(training_df: pd.DataFrame) -> pd.DataFrame:
    """Create class balance report."""
    rows = []

    total = len(training_df)

    for label, group_df in training_df.groupby("final_label", dropna=False):
        rows.append({
            "final_label": label,
            "record_count": int(len(group_df)),
            "percent": round((len(group_df) / total) * 100, 2) if total else 0,
            "real_association_count": int((group_df["record_source"] == "real_association").sum()),
            "curated_seed_count": int((group_df["record_source"] == "curated_seed_example").sum()),
            "manual_review_count": int((group_df["needs_manual_review"] == "Y").sum())
        })

    return pd.DataFrame(rows).sort_values("record_count", ascending=False)


def create_manual_review_queue(training_df: pd.DataFrame) -> pd.DataFrame:
    """Create queue for records that need manual review."""
    review_df = training_df[
        (training_df["needs_manual_review"] == "Y")
        | (training_df["final_label"] == "Unknown_Review")
    ].copy()

    review_columns = [
        "training_record_id",
        "record_source",
        "classification_text",
        "suggested_label",
        "final_label",
        "label_confidence",
        "labeling_reason",
        "rule_region_tag",
        "matched_region_keywords",
        "disease_name",
        "rsid"
    ]

    existing_cols = [col for col in review_columns if col in review_df.columns]

    return review_df[existing_cols].copy()


def run_prepare_regional_training_set() -> dict:
    paths = ensure_directories()

    input_path = paths["processed"] / INPUT_FILENAME

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_path}. Day 28 must be completed first."
        )

    input_df = pd.read_csv(input_path, dtype=str)

    if input_df.empty:
        raise ValueError("regional_tagged_associations.csv is empty.")

    real_df = build_real_records_training_df(input_df)
    seed_df = curated_seed_examples()

    training_df = sample_training_set(real_df, seed_df)

    balance_df = create_balance_report(training_df)
    manual_review_df = create_manual_review_queue(training_df)

    processed_output_path = paths["processed"] / OUTPUT_FILENAME
    outputs_output_path = paths["outputs_tables"] / OUTPUT_FILENAME
    preview_path = paths["outputs_tables"] / "training_set_preview.csv"
    balance_path = paths["outputs_tables"] / "training_set_balance.csv"
    review_path = paths["outputs_tables"] / "manual_review_queue.csv"
    metadata_path = paths["processed"] / METADATA_FILENAME

    training_df.to_csv(processed_output_path, index=False, encoding="utf-8-sig")
    training_df.to_csv(outputs_output_path, index=False, encoding="utf-8-sig")
    training_df.head(40).to_csv(preview_path, index=False, encoding="utf-8-sig")
    balance_df.to_csv(balance_path, index=False, encoding="utf-8-sig")
    manual_review_df.to_csv(review_path, index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": OUTPUT_FILENAME,
        "project_day": 29,
        "stage": "Regional Training Set Preparation",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": str(input_path),
        "training_rows": int(len(training_df)),
        "min_target_records": TARGET_MIN_RECORDS,
        "max_target_records": TARGET_MAX_RECORDS,
        "label_distribution": balance_df.to_dict(orient="records"),
        "note": "This file prepares a small labeled dataset for the Day 30 ML classifier."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "input_rows": len(input_df),
        "training_rows": len(training_df),
        "processed_output_path": str(processed_output_path),
        "outputs_output_path": str(outputs_output_path),
        "preview_path": str(preview_path),
        "balance_path": str(balance_path),
        "review_path": str(review_path),
        "metadata_path": str(metadata_path)
    }


def main() -> None:
    result = run_prepare_regional_training_set()

    print("Day 29 regional training set preparation completed.")
    print(f"Input rows: {result['input_rows']}")
    print(f"Training rows: {result['training_rows']}")
    print(f"Processed output: {result['processed_output_path']}")
    print(f"Output copy: {result['outputs_output_path']}")
    print(f"Preview: {result['preview_path']}")
    print(f"Balance report: {result['balance_path']}")
    print(f"Manual review queue: {result['review_path']}")
    print(f"Metadata: {result['metadata_path']}")


if __name__ == "__main__":
    main()
