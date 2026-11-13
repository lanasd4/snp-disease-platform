"""
ML-Based Arab/Middle East Region Classifier
"""

from datetime import datetime
import json
import re
import joblib
import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)
from core.paths import get_project_root


INPUT_FILENAME = "regional_training_set.csv"
MODEL_FILENAME = "ml_region_classifier_pipeline.joblib"
METADATA_FILENAME = "ml_region_classifier_metadata.json"

RANDOM_SEED = 42


def get_paths() -> dict:
    """Return important project paths."""
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
        "outputs_models": project_root / "outputs" / "models",
    }


def ensure_directories() -> dict:
    """Create required folders."""
    paths = get_paths()

    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)
    paths["outputs_models"].mkdir(parents=True, exist_ok=True)

    return paths


def clean_text(value):
    """Clean text and return empty string for missing values."""
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return ""

    return " ".join(text.split())


def normalize_text(value) -> str:
    """Normalize Arabic and English text before ML classification."""
    text = clean_text(value)

    if text == "":
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


def load_training_data() -> pd.DataFrame:
    paths = ensure_directories()
    training_path = paths["processed"] / INPUT_FILENAME

    if not training_path.exists():
        raise FileNotFoundError(
            f"Training set not found: {training_path}. Run the previous pipeline stage first."
        )

    df = pd.read_csv(training_path, dtype=str)

    if df.empty:
        raise ValueError("regional_training_set.csv is empty.")

    required_columns = ["classification_text", "final_label"]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column in training set: {col}")

    df["classification_text"] = df["classification_text"].apply(clean_text)

    if "normalized_classification_text" not in df.columns:
        df["normalized_classification_text"] = df["classification_text"].apply(normalize_text)
    else:
        df["normalized_classification_text"] = df["normalized_classification_text"].fillna("").apply(clean_text)

    # If normalized text is missing, rebuild it from classification_text.
    empty_mask = df["normalized_classification_text"] == ""
    df.loc[empty_mask, "normalized_classification_text"] = df.loc[
        empty_mask,
        "classification_text"
    ].apply(normalize_text)

    df["final_label"] = df["final_label"].apply(clean_text)

    df = df[
        (df["normalized_classification_text"] != "")
        & (df["final_label"] != "")
    ].copy()

    df = df.drop_duplicates(
        subset=["normalized_classification_text", "final_label"],
        keep="first"
    ).reset_index(drop=True)

    if df.empty:
        raise ValueError("No valid training rows after cleaning.")

    return df


def build_pipeline() -> Pipeline:
    """Build TF-IDF + Logistic Regression pipeline."""
    pipeline = Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),
                min_df=1,
                max_df=0.95
            )
        ),
        (
            "classifier",
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=RANDOM_SEED
            )
        )
    ])

    return pipeline


def safe_train_test_split(df: pd.DataFrame):
    """Split data into train/test if possible."""
    label_counts = df["final_label"].value_counts()

    can_stratify = (
        len(label_counts) >= 2
        and label_counts.min() >= 2
        and len(df) >= 12
    )

    if can_stratify:
        train_df, test_df = train_test_split(
            df,
            test_size=0.25,
            random_state=RANDOM_SEED,
            stratify=df["final_label"]
        )

        split_note = "Stratified train/test split was used."

    else:
        train_df = df.copy()
        test_df = df.copy()
        split_note = "Full dataset evaluation was used because stratified split was not possible."

    return train_df, test_df, split_note


def calculate_metrics(y_true, y_pred) -> dict:
    """Calculate accuracy, precision, recall, and F1."""
    accuracy = accuracy_score(y_true, y_pred)

    precision_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="macro",
        zero_division=0
    )

    precision_weighted, recall_weighted, f1_weighted, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="weighted",
        zero_division=0
    )

    return {
        "accuracy": round(float(accuracy), 4),
        "precision_macro": round(float(precision_macro), 4),
        "recall_macro": round(float(recall_macro), 4),
        "f1_macro": round(float(f1_macro), 4),
        "precision_weighted": round(float(precision_weighted), 4),
        "recall_weighted": round(float(recall_weighted), 4),
        "f1_weighted": round(float(f1_weighted), 4)
    }


def metrics_to_dataframe(metrics: dict, train_size: int, test_size: int, split_note: str) -> pd.DataFrame:
    """Convert metrics dictionary to DataFrame."""
    rows = []

    for metric_name, value in metrics.items():
        rows.append({
            "metric": metric_name,
            "value": value,
            "train_size": train_size,
            "test_size": test_size,
            "split_note": split_note
        })

    return pd.DataFrame(rows)


def classification_report_to_dataframe(y_true, y_pred) -> pd.DataFrame:
    """Convert sklearn classification report to DataFrame."""
    report_dict = classification_report(
        y_true,
        y_pred,
        output_dict=True,
        zero_division=0
    )

    rows = []

    for label, scores in report_dict.items():
        if isinstance(scores, dict):
            row = {"label": label}
            row.update(scores)
            rows.append(row)
        else:
            rows.append({
                "label": label,
                "score": scores
            })

    return pd.DataFrame(rows)


def confusion_matrix_to_dataframe(y_true, y_pred, labels) -> pd.DataFrame:
    """Convert confusion matrix to DataFrame."""
    matrix = confusion_matrix(y_true, y_pred, labels=labels)

    matrix_df = pd.DataFrame(
        matrix,
        index=[f"actual_{label}" for label in labels],
        columns=[f"predicted_{label}" for label in labels]
    )

    matrix_df = matrix_df.reset_index().rename(columns={"index": "actual_label"})

    return matrix_df


def build_test_predictions_df(test_df: pd.DataFrame, y_pred) -> pd.DataFrame:
    """Create DataFrame of test predictions."""
    output_df = test_df.copy()
    output_df["predicted_label"] = y_pred
    output_df["prediction_correct"] = output_df["final_label"] == output_df["predicted_label"]

    selected_columns = [
        "classification_text",
        "normalized_classification_text",
        "final_label",
        "predicted_label",
        "prediction_correct",
        "record_source",
        "label_confidence",
        "needs_manual_review"
    ]

    existing_columns = [col for col in selected_columns if col in output_df.columns]

    return output_df[existing_columns].copy()


def predict_manual_examples(model: Pipeline) -> pd.DataFrame:
    """Run manual prediction examples for interpretation."""
    examples = [
        "Saudi Arabian cohort study",
        "Qatari population with asthma",
        "Palestinian families from the West Bank",
        "Middle Eastern ancestry participants",
        "European ancestry sample",
        "Han Chinese population",
        "Japanese cohort",
        "Unknown population",
        "No regional text available",
        "مرضى من فلسطين والاردن",
        "عينة من الشرق الاوسط",
        "سكان اوروبيون"
    ]

    normalized_examples = [normalize_text(text) for text in examples]
    predictions = model.predict(normalized_examples)

    rows = []

    for text, normalized, prediction in zip(examples, normalized_examples, predictions):
        rows.append({
            "input_text": text,
            "normalized_text": normalized,
            "predicted_label": prediction
        })

    return pd.DataFrame(rows)


def run_ml_region_classifier() -> dict:
    paths = ensure_directories()

    training_df = load_training_data()

    train_df, test_df, split_note = safe_train_test_split(training_df)

    model = build_pipeline()

    X_train = train_df["normalized_classification_text"]
    y_train = train_df["final_label"]

    X_test = test_df["normalized_classification_text"]
    y_test = test_df["final_label"]

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    metrics = calculate_metrics(y_test, y_pred)

    labels = sorted(training_df["final_label"].dropna().unique().tolist())

    metrics_df = metrics_to_dataframe(
        metrics=metrics,
        train_size=len(train_df),
        test_size=len(test_df),
        split_note=split_note
    )

    report_df = classification_report_to_dataframe(y_test, y_pred)
    confusion_df = confusion_matrix_to_dataframe(y_test, y_pred, labels)
    predictions_df = build_test_predictions_df(test_df, y_pred)
    manual_predictions_df = predict_manual_examples(model)

    model_summary_df = pd.DataFrame([
        {
            "item": "model_type",
            "value": "TF-IDF + Logistic Regression"
        },
        {
            "item": "input_file",
            "value": str(paths["processed"] / INPUT_FILENAME)
        },
        {
            "item": "training_rows_total",
            "value": len(training_df)
        },
        {
            "item": "train_size",
            "value": len(train_df)
        },
        {
            "item": "test_size",
            "value": len(test_df)
        },
        {
            "item": "labels",
            "value": ", ".join(labels)
        },
        {
            "item": "split_note",
            "value": split_note
        }
    ])

    metrics_path = paths["outputs_tables"] / "region_classifier_metrics.csv"
    report_path = paths["outputs_tables"] / "classification_report.csv"
    confusion_path = paths["outputs_tables"] / "confusion_matrix.csv"
    predictions_path = paths["outputs_tables"] / "ml_classifier_test_predictions.csv"
    manual_examples_path = paths["outputs_tables"] / "manual_prediction_examples.csv"
    summary_path = paths["outputs_tables"] / "model_summary.csv"

    model_path = paths["outputs_models"] / MODEL_FILENAME
    metadata_path = paths["processed"] / METADATA_FILENAME

    metrics_df.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    report_df.to_csv(report_path, index=False, encoding="utf-8-sig")
    confusion_df.to_csv(confusion_path, index=False, encoding="utf-8-sig")
    predictions_df.to_csv(predictions_path, index=False, encoding="utf-8-sig")
    manual_predictions_df.to_csv(manual_examples_path, index=False, encoding="utf-8-sig")
    model_summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    joblib.dump(model, model_path)

    metadata = {
        "file_name": MODEL_FILENAME,
        "stage": "Initial ML Arab/Middle East Region Classifier",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model_type": "TF-IDF + Logistic Regression",
        "training_rows_total": int(len(training_df)),
        "train_size": int(len(train_df)),
        "test_size": int(len(test_df)),
        "labels": labels,
        "metrics": metrics,
        "split_note": split_note,
        "model_path": str(model_path),
        "note": "Prototype ML classifier for regional text classification. Not a definitive population genetics classifier."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "training_rows_total": len(training_df),
        "train_size": len(train_df),
        "test_size": len(test_df),
        "labels": labels,
        "metrics": metrics,
        "metrics_path": str(metrics_path),
        "report_path": str(report_path),
        "confusion_path": str(confusion_path),
        "predictions_path": str(predictions_path),
        "manual_examples_path": str(manual_examples_path),
        "summary_path": str(summary_path),
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "split_note": split_note
    }


def load_saved_model():
    paths = ensure_directories()
    model_path = paths["outputs_models"] / MODEL_FILENAME

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    return joblib.load(model_path)


def predict_region_label(text: str) -> dict:
    """Predict regional label for one input text using saved model."""
    model = load_saved_model()
    normalized = normalize_text(text)
    prediction = model.predict([normalized])[0]

    result = {
        "input_text": text,
        "normalized_text": normalized,
        "predicted_label": prediction
    }

    if hasattr(model.named_steps["classifier"], "predict_proba"):
        probabilities = model.predict_proba([normalized])[0]
        labels = model.named_steps["classifier"].classes_

        result["prediction_probabilities"] = {
            label: round(float(prob), 4)
            for label, prob in zip(labels, probabilities)
        }

    return result


def main() -> None:
    result = run_ml_region_classifier()

    print("ML region classifier completed.")
    print(f"Training rows total: {result['training_rows_total']}")
    print(f"Train size: {result['train_size']}")
    print(f"Test size: {result['test_size']}")
    print(f"Labels: {', '.join(result['labels'])}")
    print(f"Split note: {result['split_note']}")
    print("Metrics:")
    for key, value in result["metrics"].items():
        print(f"  {key}: {value}")
    print(f"Metrics file: {result['metrics_path']}")
    print(f"Classification report: {result['report_path']}")
    print(f"Confusion matrix: {result['confusion_path']}")
    print(f"Predictions: {result['predictions_path']}")
    print(f"Manual examples: {result['manual_examples_path']}")
    print(f"Model file: {result['model_path']}")
    print(f"Metadata: {result['metadata_path']}")


if __name__ == "__main__":
    main()
