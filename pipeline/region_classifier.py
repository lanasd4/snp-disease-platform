"""
Rule-Based Arab/Middle East Region Classifier
"""

from pathlib import Path
from datetime import datetime
import json
import re
import pandas as pd
from core.paths import get_project_root


OUTPUT_FILENAME = "regional_tagged_associations.csv"
METADATA_FILENAME = "regional_tagged_associations_metadata.json"


ARAB_MIDDLE_EAST_KEYWORDS = {
    "arab": [
        "arab", "arabian", "arabic", "arab-related",
        "عرب", "عربي", "العرب", "العربية"
    ],
    "middle_east": [
        "middle east", "middle eastern", "mena", "near east",
        "شرق اوسط", "الشرق الاوسط", "شرق اوسطي"
    ],
    "gulf": [
        "gulf", "gcc", "arabian gulf", "persian gulf",
        "الخليج", "دول الخليج", "مجلس التعاون"
    ],
    "levant": [
        "levant", "levantine", "بلاد الشام", "الشام"
    ],
    "north_africa": [
        "north africa", "north african", "maghreb", "maghrebi",
        "شمال افريقيا", "المغرب العربي"
    ],
    "palestine": [
        "palestine", "palestinian", "فلسطين", "فلسطيني", "الفلسطيني"
    ],
    "jordan": [
        "jordan", "jordanian", "الاردن", "اردن", "اردني"
    ],
    "lebanon": [
        "lebanon", "lebanese", "لبنان", "لبناني"
    ],
    "syria": [
        "syria", "syrian", "سوريا", "سوري"
    ],
    "iraq": [
        "iraq", "iraqi", "العراق", "عراقي"
    ],
    "saudi": [
        "saudi", "saudi arabia", "saudian", "ksa",
        "السعودية", "سعودي", "المملكة العربية السعودية"
    ],
    "qatar": [
        "qatar", "qatari", "قطر", "قطري"
    ],
    "kuwait": [
        "kuwait", "kuwaiti", "الكويت", "كويتي"
    ],
    "uae": [
        "uae", "united arab emirates", "emirates", "emirati",
        "الامارات", "اماراتي", "الامارات العربية المتحدة"
    ],
    "oman": [
        "oman", "omani", "عمان", "عماني"
    ],
    "bahrain": [
        "bahrain", "bahraini", "البحرين", "بحريني"
    ],
    "yemen": [
        "yemen", "yemeni", "اليمن", "يمني"
    ],
    "egypt": [
        "egypt", "egyptian", "مصر", "مصري"
    ],
    "morocco": [
        "morocco", "moroccan", "المغرب", "مغربي"
    ],
    "tunisia": [
        "tunisia", "tunisian", "تونس", "تونسي"
    ],
    "algeria": [
        "algeria", "algerian", "الجزائر", "جزائري"
    ],
    "libya": [
        "libya", "libyan", "ليبيا", "ليبي"
    ],
    "sudan": [
        "sudan", "sudanese", "السودان", "سوداني"
    ],
    "mauritania": [
        "mauritania", "mauritanian", "موريتانيا", "موريتاني"
    ]
}


NON_ARAB_MIDDLE_EAST_KEYWORDS = {
    "iran": ["iran", "iranian", "persian", "ايران", "ايراني", "فارسي"],
    "turkey": ["turkey", "turkish", "تركيا", "تركي"],
    "israel": ["israel", "israeli", "اسرائيل", "اسرائيلي"]
}


OTHER_REGION_KEYWORDS = {
    "europe": [
        "europe", "european", "caucasian", "white british",
        "فنلندي", "بريطاني", "اوروبي"
    ],
    "east_asia": [
        "east asian", "chinese", "china", "japanese", "japan",
        "korean", "korea", "han chinese"
    ],
    "south_asia": [
        "south asian", "indian", "india", "pakistani", "pakistan",
        "bangladeshi", "sri lankan"
    ],
    "africa_other": [
        "african american", "sub-saharan", "nigerian", "kenyan", "ghanaian"
    ],
    "latin_america": [
        "hispanic", "latino", "mexican", "brazilian", "latin american"
    ]
}


UNKNOWN_WORDS = [
    "unknown", "not reported", "not available", "na", "n/a",
    "غير معروف", "غير محدد"
]


TEXT_FIELDS_FOR_CLASSIFICATION = [
    "population_label",
    "region",
    "ancestry",
    "country",
    "study_title",
    "source_database_clean",
    "source_database",
    "journal"
]


def get_paths() -> dict:
    """Return important project paths."""
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_directories() -> dict:
    """Create required output folders."""
    paths = get_paths()

    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)

    return paths


def clean_text(value):
    """Clean text and return None for empty-like values."""
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def normalize_text(value) -> str:
    """Normalize Arabic and English text for rule matching."""
    text = clean_text(value)

    if text is None:
        return ""

    text = text.lower()

    # Remove Arabic diacritics
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


def flatten_keyword_map(keyword_map: dict) -> list:
    """Flatten keyword dictionary into list of tuples:"""
    rows = []

    for category, keywords in keyword_map.items():
        for keyword in keywords:
            rows.append((category, keyword, normalize_text(keyword)))

    return rows


ARAB_KEYWORD_ROWS = flatten_keyword_map(ARAB_MIDDLE_EAST_KEYWORDS)
NON_ARAB_ME_ROWS = flatten_keyword_map(NON_ARAB_MIDDLE_EAST_KEYWORDS)
OTHER_KEYWORD_ROWS = flatten_keyword_map(OTHER_REGION_KEYWORDS)
UNKNOWN_KEYWORD_ROWS = [normalize_text(item) for item in UNKNOWN_WORDS]


def keyword_found(normalized_text: str, normalized_keyword: str) -> bool:
    """Check keyword existence using safe word-boundary-like matching."""
    if not normalized_text or not normalized_keyword:
        return False

    if " " in normalized_keyword:
        return normalized_keyword in normalized_text

    tokens = normalized_text.split()
    return normalized_keyword in tokens or normalized_keyword in normalized_text


def collect_record_text(row: pd.Series) -> dict:
    """Collect available text fields from a record for classification."""
    field_texts = {}

    for field in TEXT_FIELDS_FOR_CLASSIFICATION:
        if field in row.index:
            value = clean_text(row.get(field))
            if value:
                field_texts[field] = value

    combined_text = " | ".join(field_texts.values())

    return {
        "field_texts": field_texts,
        "combined_text": combined_text,
        "normalized_combined_text": normalize_text(combined_text)
    }


def classify_region_text(text: str) -> dict:
    """Classify a text as Arab/Middle East, Non-Arab Middle East, Other, or Unknown."""
    normalized = normalize_text(text)

    if normalized == "":
        return {
            "region_tag_rule": "Unknown",
            "region_subtag_rule": "No regional text",
            "is_arab_related_rule": "N",
            "rule_confidence": "Low",
            "matched_region_keywords": "",
            "matched_keyword_categories": "",
            "classification_reason": "No regional or population text was available."
        }

    matched_arab = []
    matched_arab_categories = []

    for category, keyword, normalized_keyword in ARAB_KEYWORD_ROWS:
        if keyword_found(normalized, normalized_keyword):
            matched_arab.append(keyword)
            matched_arab_categories.append(category)

    matched_non_arab_me = []
    matched_non_arab_me_categories = []

    for category, keyword, normalized_keyword in NON_ARAB_ME_ROWS:
        if keyword_found(normalized, normalized_keyword):
            matched_non_arab_me.append(keyword)
            matched_non_arab_me_categories.append(category)

    matched_other = []
    matched_other_categories = []

    for category, keyword, normalized_keyword in OTHER_KEYWORD_ROWS:
        if keyword_found(normalized, normalized_keyword):
            matched_other.append(keyword)
            matched_other_categories.append(category)

    matched_unknown = []

    for keyword in UNKNOWN_KEYWORD_ROWS:
        if keyword_found(normalized, keyword):
            matched_unknown.append(keyword)

    if matched_arab:
        unique_keywords = sorted(set(matched_arab))
        unique_categories = sorted(set(matched_arab_categories))

        return {
            "region_tag_rule": "Arab/Middle East",
            "region_subtag_rule": ", ".join(unique_categories),
            "is_arab_related_rule": "Y",
            "rule_confidence": "High",
            "matched_region_keywords": ", ".join(unique_keywords),
            "matched_keyword_categories": ", ".join(unique_categories),
            "classification_reason": "Arab or Middle East keyword was found."
        }

    if matched_non_arab_me:
        unique_keywords = sorted(set(matched_non_arab_me))
        unique_categories = sorted(set(matched_non_arab_me_categories))

        return {
            "region_tag_rule": "Middle East - Non-Arab/Regional",
            "region_subtag_rule": ", ".join(unique_categories),
            "is_arab_related_rule": "Y",
            "rule_confidence": "Medium",
            "matched_region_keywords": ", ".join(unique_keywords),
            "matched_keyword_categories": ", ".join(unique_categories),
            "classification_reason": "Non-Arab Middle East regional keyword was found."
        }

    if matched_other:
        unique_keywords = sorted(set(matched_other))
        unique_categories = sorted(set(matched_other_categories))

        return {
            "region_tag_rule": "Other",
            "region_subtag_rule": ", ".join(unique_categories),
            "is_arab_related_rule": "N",
            "rule_confidence": "High",
            "matched_region_keywords": ", ".join(unique_keywords),
            "matched_keyword_categories": ", ".join(unique_categories),
            "classification_reason": "Non-Arab/non-Middle-East population keyword was found."
        }

    if matched_unknown:
        return {
            "region_tag_rule": "Unknown",
            "region_subtag_rule": "Unknown/Not reported",
            "is_arab_related_rule": "N",
            "rule_confidence": "Low",
            "matched_region_keywords": ", ".join(sorted(set(matched_unknown))),
            "matched_keyword_categories": "unknown",
            "classification_reason": "Text indicates that region/population is unknown or not reported."
        }

    return {
        "region_tag_rule": "Unknown",
        "region_subtag_rule": "No rule matched",
        "is_arab_related_rule": "N",
        "rule_confidence": "Low",
        "matched_region_keywords": "",
        "matched_keyword_categories": "",
        "classification_reason": "No regional rule matched the available text."
    }


def classify_record(row: pd.Series) -> dict:
    """Classify a DataFrame row using available regional fields."""
    collected = collect_record_text(row)
    classification = classify_region_text(collected["combined_text"])

    classification["classification_text_used"] = collected["combined_text"]
    classification["classification_normalized_text"] = collected["normalized_combined_text"]

    field_names = sorted(collected["field_texts"].keys())
    classification["classification_fields_used"] = ", ".join(field_names)

    return classification


def choose_input_file(paths: dict) -> Path:
    ranked_path = paths["processed"] / "ranked_associations_initial.csv"
    features_path = paths["processed"] / "ranking_features.csv"

    if ranked_path.exists():
        return ranked_path

    if features_path.exists():
        return features_path

    raise FileNotFoundError(
        "No suitable input file found. Expected ranked_associations_initial.csv or ranking_features.csv."
    )


def run_rule_based_region_classification() -> dict:
    paths = ensure_directories()
    input_path = choose_input_file(paths)

    input_df = pd.read_csv(input_path, dtype=str)

    if input_df.empty:
        raise ValueError(f"Input file is empty: {input_path}")

    classification_rows = []

    for _, row in input_df.iterrows():
        classification_rows.append(classify_record(row))

    classification_df = pd.DataFrame(classification_rows)

    tagged_df = pd.concat(
        [input_df.reset_index(drop=True), classification_df.reset_index(drop=True)],
        axis=1
    )

    processed_output_path = paths["processed"] / OUTPUT_FILENAME
    metadata_path = paths["processed"] / METADATA_FILENAME

    output_copy_path = paths["outputs_tables"] / OUTPUT_FILENAME
    preview_path = paths["outputs_tables"] / "regional_tagged_preview.csv"
    arab_preview_path = paths["outputs_tables"] / "arab_middle_east_records_preview.csv"
    summary_path = paths["outputs_tables"] / "regional_tagging_summary.csv"

    tagged_df.to_csv(processed_output_path, index=False, encoding="utf-8-sig")
    tagged_df.to_csv(output_copy_path, index=False, encoding="utf-8-sig")
    tagged_df.head(40).to_csv(preview_path, index=False, encoding="utf-8-sig")

    arab_df = tagged_df[
        tagged_df["is_arab_related_rule"].astype(str).str.upper() == "Y"
    ].copy()

    arab_df.head(40).to_csv(arab_preview_path, index=False, encoding="utf-8-sig")

    summary_df = (
        tagged_df
        .groupby(["region_tag_rule", "is_arab_related_rule", "rule_confidence"], dropna=False)
        .size()
        .reset_index(name="record_count")
        .sort_values("record_count", ascending=False)
    )

    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    tests_result = run_region_tagging_tests(save_output=True)

    metadata = {
        "file_name": OUTPUT_FILENAME,
        "stage": "Rule-Based Arab/Middle East Region Classification",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": str(input_path),
        "output_rows": int(len(tagged_df)),
        "arab_middle_east_related_rows": int(len(arab_df)),
        "summary_path": str(summary_path),
        "tests_output_path": tests_result.get("output_path"),
        "note": "Rule-based classification only."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "input_path": str(input_path),
        "output_rows": len(tagged_df),
        "arab_rows": len(arab_df),
        "processed_output_path": str(processed_output_path),
        "output_copy_path": str(output_copy_path),
        "preview_path": str(preview_path),
        "arab_preview_path": str(arab_preview_path),
        "summary_path": str(summary_path),
        "metadata_path": str(metadata_path),
        "tests_output_path": tests_result.get("output_path")
    }


def run_region_tagging_tests(save_output: bool = True) -> dict:
    """Run rule-based test examples."""
    paths = ensure_directories()

    test_cases = [
        {
            "test_text": "Qatari population with type 2 diabetes",
            "expected_tag": "Arab/Middle East"
        },
        {
            "test_text": "Saudi Arabian cohort study",
            "expected_tag": "Arab/Middle East"
        },
        {
            "test_text": "Middle Eastern ancestry participants",
            "expected_tag": "Arab/Middle East"
        },
        {
            "test_text": "Palestinian families from the West Bank",
            "expected_tag": "Arab/Middle East"
        },
        {
            "test_text": "European ancestry sample",
            "expected_tag": "Other"
        },
        {
            "test_text": "East Asian population",
            "expected_tag": "Other"
        },
        {
            "test_text": "Iranian cohort",
            "expected_tag": "Middle East - Non-Arab/Regional"
        },
        {
            "test_text": "Unknown population",
            "expected_tag": "Unknown"
        },
        {
            "test_text": "دراسة على عينة سعودية",
            "expected_tag": "Arab/Middle East"
        },
        {
            "test_text": "مرضى من فلسطين والاردن",
            "expected_tag": "Arab/Middle East"
        },
        {
            "test_text": "عينة من الشرق الاوسط",
            "expected_tag": "Arab/Middle East"
        },
        {
            "test_text": "سكان اوروبيون",
            "expected_tag": "Other"
        }
    ]

    rows = []

    for case in test_cases:
        result = classify_region_text(case["test_text"])

        rows.append({
            "test_text": case["test_text"],
            "expected_tag": case["expected_tag"],
            "predicted_tag": result["region_tag_rule"],
            "is_arab_related_rule": result["is_arab_related_rule"],
            "rule_confidence": result["rule_confidence"],
            "matched_region_keywords": result["matched_region_keywords"],
            "classification_reason": result["classification_reason"],
            "test_passed": result["region_tag_rule"] == case["expected_tag"]
        })

    tests_df = pd.DataFrame(rows)

    output_path = paths["outputs_tables"] / "regional_tagging_tests.csv"

    if save_output:
        tests_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    passed_count = int(tests_df["test_passed"].sum())
    total_count = int(len(tests_df))

    return {
        "total_tests": total_count,
        "passed_tests": passed_count,
        "failed_tests": total_count - passed_count,
        "output_path": str(output_path)
    }


def main() -> None:
    result = run_rule_based_region_classification()

    print("Rule-based regional classification completed.")
    print(f"Input file: {result['input_path']}")
    print(f"Output rows: {result['output_rows']}")
    print(f"Arab/Middle East related rows: {result['arab_rows']}")
    print(f"Processed output: {result['processed_output_path']}")
    print(f"Output copy: {result['output_copy_path']}")
    print(f"Preview: {result['preview_path']}")
    print(f"Arab/Middle East preview: {result['arab_preview_path']}")
    print(f"Summary: {result['summary_path']}")
    print(f"Tests: {result['tests_output_path']}")
    print(f"Metadata: {result['metadata_path']}")


if __name__ == "__main__":
    main()
