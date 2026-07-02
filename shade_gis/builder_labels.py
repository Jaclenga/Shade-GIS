import math
import re
from typing import Any

import pandas as pd
import streamlit as st


REVIEW_STATUS_NAMES = {
    "Unlabeled",
    "Needs Review",
    "Crowd Reviewed",
    "Expert Reviewed",
    "Accepted",
    "Disputed",
    "Archived",
}


def normalize_review_status(value: Any) -> str:
    if pd.isna(value) or not str(value).strip():
        return "Unlabeled"
    text = str(value).strip()
    return text if text in REVIEW_STATUS_NAMES else "Needs Review"


def stop_picker_label(row: pd.Series) -> str:
    stop_id = str(row.get("stop_id", "")).strip()
    stop_name = str(row.get("stop_name", "")).strip() or "Unnamed stop"
    routes = str(row.get("routes", "")).strip()
    suffix = f" | routes {routes}" if routes else ""
    return f"{stop_name} ({stop_id}){suffix}"


def taxonomy_names(taxonomy: list[dict[str, Any]]) -> list[str]:
    names = [str(item.get("name", "")).strip() for item in taxonomy if str(item.get("name", "")).strip()]
    return names or ["Needs Review"]


def label_source_code(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "manual").strip().lower()).strip("_") or "manual"


def raw_label_summary(labels: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    labeled_stop_count = labels["stop_id"].nunique() if not labels.empty and "stop_id" in labels.columns else 0
    conflicting_stops = 0
    if not labels.empty and {"stop_id", "shade_category"}.issubset(labels.columns):
        category_counts = labels.dropna(subset=["shade_category"]).groupby("stop_id")["shade_category"].nunique()
        conflicting_stops = int((category_counts > 1).sum())
    checks = [
        ("Raw labels stored", len(labels)),
        ("Stops with raw labels", int(labeled_stop_count)),
        ("Stops without raw labels", max(len(stops) - int(labeled_stop_count), 0)),
        ("Stops with conflicting raw labels", conflicting_stops),
    ]
    return pd.DataFrame(checks, columns=["Check", "Value"])


def clean_label_values(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    if labels.empty or label_column not in labels.columns or "stop_id" not in labels.columns:
        return pd.DataFrame(columns=list(labels.columns) if not labels.empty else ["stop_id", label_column])
    clean = labels.copy()
    clean["stop_id"] = clean["stop_id"].fillna("").astype(str).str.strip()
    clean[label_column] = clean[label_column].fillna("").astype(str).str.strip()
    clean = clean[(clean["stop_id"] != "") & (clean[label_column] != "")]
    return clean


def majority_label_table(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame(
            columns=[
                "stop_id",
                "majority_label",
                "label_count",
                "majority_count",
                "agreement_pct",
                "disagreement_flag",
                "tied_majority",
            ]
        )
    rows = []
    for stop_id, group in clean.groupby("stop_id", sort=True):
        counts = group[label_column].value_counts()
        max_count = int(counts.max())
        winners = sorted(counts[counts == max_count].index.astype(str).tolist())
        total = int(counts.sum())
        rows.append(
            {
                "stop_id": stop_id,
                "majority_label": "; ".join(winners),
                "label_count": total,
                "majority_count": max_count,
                "agreement_pct": round(max_count / total * 100, 1) if total else 0.0,
                "disagreement_flag": len(counts) > 1,
                "tied_majority": len(winners) > 1,
            }
        )
    return pd.DataFrame(rows)


def label_rater_key(row: pd.Series) -> str:
    labeler_id = str(row.get("labeler_id", "") or "").strip()
    if labeler_id:
        return labeler_id
    role = str(row.get("labeler_role", "") or "").strip()
    source = str(row.get("source", "") or "").strip()
    return f"{role or 'unknown'}:{source or 'manual'}"


def latest_labels_by_rater(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame(columns=["stop_id", "rater", label_column])
    clean = clean.copy()
    clean["rater"] = clean.apply(label_rater_key, axis=1)
    if "created_at" in clean.columns:
        clean = clean.sort_values("created_at")
    return clean.drop_duplicates(subset=["stop_id", "rater"], keep="last")


def cohen_kappa_for_pair(left: pd.Series, right: pd.Series, categories: list[str]) -> float | None:
    paired = pd.DataFrame({"left": left, "right": right}).dropna()
    if paired.empty:
        return None
    observed = float((paired["left"] == paired["right"]).mean())
    total = len(paired)
    expected = 0.0
    for category in categories:
        expected += (paired["left"].eq(category).sum() / total) * (paired["right"].eq(category).sum() / total)
    if math.isclose(1.0 - expected, 0.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1.0 - expected)


def average_pairwise_cohen_kappa(labels: pd.DataFrame, label_column: str = "shade_category") -> tuple[float | None, int]:
    latest = latest_labels_by_rater(labels, label_column)
    if latest.empty or latest["rater"].nunique() < 2:
        return None, 0
    matrix = latest.pivot(index="stop_id", columns="rater", values=label_column)
    categories = sorted(latest[label_column].dropna().astype(str).unique().tolist())
    kappas = []
    raters = list(matrix.columns)
    for left_index, left_rater in enumerate(raters):
        for right_rater in raters[left_index + 1 :]:
            paired = matrix[[left_rater, right_rater]].dropna()
            if len(paired) < 2:
                continue
            kappa = cohen_kappa_for_pair(paired[left_rater], paired[right_rater], categories)
            if kappa is not None:
                kappas.append(kappa)
    if not kappas:
        return None, 0
    return float(sum(kappas) / len(kappas)), len(kappas)


def category_count_matrix(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame()
    return pd.crosstab(clean["stop_id"], clean[label_column])


def fleiss_kappa(labels: pd.DataFrame, label_column: str = "shade_category") -> float | None:
    counts = category_count_matrix(labels, label_column)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    total_assignments = float(item_totals.sum())
    p_i = ((counts.pow(2).sum(axis=1) - item_totals) / (item_totals * (item_totals - 1))).fillna(0)
    p_bar = float((p_i * item_totals / total_assignments).sum())
    category_props = counts.sum(axis=0) / total_assignments
    p_e = float(category_props.pow(2).sum())
    if math.isclose(1.0 - p_e, 0.0):
        return 1.0 if math.isclose(p_bar, 1.0) else None
    return (p_bar - p_e) / (1.0 - p_e)


def krippendorff_alpha_nominal(labels: pd.DataFrame, label_column: str = "shade_category") -> float | None:
    counts = category_count_matrix(labels, label_column)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    observed_terms = []
    for stop_id, row in counts.iterrows():
        n_i = float(item_totals.loc[stop_id])
        observed_terms.append(float((row * (n_i - row)).sum() / (n_i - 1)))
    observed = sum(observed_terms) / float(item_totals.sum())
    category_totals = counts.sum(axis=0)
    total = float(category_totals.sum())
    if total <= 1:
        return None
    expected = float((category_totals * (total - category_totals)).sum() / (total - 1) / total)
    if math.isclose(expected, 0.0):
        return 1.0 if math.isclose(observed, 0.0) else None
    return 1.0 - (observed / expected)


def format_metric_value(value: float | None, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "Not enough data"
    return f"{float(value):.{digits}f}"


def agreement_metric_summary(labels: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    majority = majority_label_table(labels)
    labeled_stops = int(majority["stop_id"].nunique()) if not majority.empty else 0
    multi_label_stops = int((majority["label_count"] >= 2).sum()) if not majority.empty else 0
    disagreement_stops = int(majority["disagreement_flag"].sum()) if not majority.empty else 0
    average_agreement = (
        float(majority["agreement_pct"].mean()) if not majority.empty and "agreement_pct" in majority else None
    )
    cohen, cohen_pairs = average_pairwise_cohen_kappa(labels)
    return pd.DataFrame(
        [
            ("Stops with labels", labeled_stops),
            ("Stops with 2+ labels", multi_label_stops),
            ("Stops with disagreement", disagreement_stops),
            ("Mean majority agreement", f"{average_agreement:.1f}%" if average_agreement is not None else "Not enough data"),
            ("Average pairwise Cohen kappa", format_metric_value(cohen)),
            ("Cohen rater pairs compared", cohen_pairs),
            ("Fleiss kappa", format_metric_value(fleiss_kappa(labels))),
            ("Krippendorff alpha", format_metric_value(krippendorff_alpha_nominal(labels))),
        ],
        columns=["Metric", "Value"],
    )


def render_agreement_metrics(labels: pd.DataFrame, stops: pd.DataFrame) -> None:
    st.markdown("#### Agreement Metrics")
    if labels.empty:
        st.info("Submit raw labels from at least two assessments to compute agreement metrics.")
        return
    st.dataframe(agreement_metric_summary(labels, stops), width="stretch", hide_index=True)
    majority = majority_label_table(labels)
    if not majority.empty:
        display = majority.sort_values(["disagreement_flag", "agreement_pct", "stop_id"], ascending=[False, True, True])
        st.dataframe(display, width="stretch", hide_index=True)


def split_list_field(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    pieces = re.split(r"[;,]", str(value))
    return [piece.strip() for piece in pieces if piece.strip()]


def stop_review_snapshot(stop: pd.Series | dict[str, Any]) -> dict[str, Any]:
    return {
        "shade_category": str(stop.get("shading", "") or ""),
        "shade_coverage": str(stop.get("shade_coverage", "") or ""),
        "shade_sources": str(stop.get("shade_sources", "") or ""),
        "confidence": stop.get("confidence", None),
        "review_status": str(stop.get("review_status", "Unlabeled") or "Unlabeled"),
    }


def review_queue_table(stops: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    if stops.empty or "stop_id" not in stops.columns:
        return pd.DataFrame()
    queue = stops.copy()
    queue["stop_id"] = queue["stop_id"].astype(str)
    if "review_status" not in queue.columns:
        queue["review_status"] = "Unlabeled"
    queue["review_status"] = queue["review_status"].apply(normalize_review_status)
    for column in ["shading", "stop_name", "routes", "municipality"]:
        if column not in queue.columns:
            queue[column] = ""

    majority = majority_label_table(labels)
    if not majority.empty:
        majority["stop_id"] = majority["stop_id"].astype(str)
        queue = queue.merge(majority, on="stop_id", how="left")
    for column, fallback in [
        ("majority_label", ""),
        ("label_count", 0),
        ("majority_count", 0),
        ("agreement_pct", 0.0),
        ("disagreement_flag", False),
        ("tied_majority", False),
    ]:
        if column not in queue.columns:
            queue[column] = fallback
        queue[column] = queue[column].fillna(fallback)

    priority_rank = {status: index for index, status in enumerate(["Disputed", "Needs Review", "Unlabeled"])}
    queue["queue_rank"] = queue["review_status"].map(priority_rank).fillna(10)
    if "priority_score" in queue.columns:
        priority_score = pd.to_numeric(queue["priority_score"], errors="coerce").fillna(0)
    else:
        priority_score = pd.Series(0.0, index=queue.index)
        queue["priority_score"] = priority_score
    agreement_gap = 100 - pd.to_numeric(queue["agreement_pct"], errors="coerce").fillna(100)
    queue["queue_score"] = (
        (10 - queue["queue_rank"]).clip(lower=0) * 100
        + queue["disagreement_flag"].astype(bool).astype(int) * 60
        + agreement_gap
        + priority_score.clip(lower=0)
    )
    return queue.sort_values(["queue_score", "priority_score", "stop_name"], ascending=[False, False, True])


def review_queue_label(row: pd.Series) -> str:
    status = str(row.get("review_status", "Unlabeled") or "Unlabeled")
    label_count = int(float(row.get("label_count", 0) or 0))
    disagreement = "disputed labels" if bool(row.get("disagreement_flag", False)) else f"{label_count} label(s)"
    return f"{stop_picker_label(row)} - {status} - {disagreement}"

