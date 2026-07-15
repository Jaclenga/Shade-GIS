from __future__ import annotations

import copy
import re
from typing import Any


SHADE_COVERAGE_OPTIONS = ["No Shade", "Limited Shade", "Significant Shade"]
SHADE_SOURCE_OPTIONS = ["Natural", "Purpose-built", "Incidental"]

SHADE_COVERAGE_TAXONOMY = [
    {
        "shade_coverage": "No Shade",
        "operational_definition": "No shade visibly reaches the waiting area.",
    },
    {
        "shade_coverage": "Limited Shade",
        "operational_definition": "Shade visibly covers part of the waiting area, but not most of it.",
    },
    {
        "shade_coverage": "Significant Shade",
        "operational_definition": "Shade visibly covers most of the waiting area or seating area.",
    },
]

SHADE_SOURCE_TAXONOMY = [
    {
        "shade_source": "Natural",
        "operational_definition": "Trees, palms, hedges, or other vegetation visibly shade the waiting area.",
    },
    {
        "shade_source": "Purpose-built",
        "operational_definition": (
            "A designated, purpose-built bus shelter, awning, canopy, overhang, or similar passenger shelter "
            "visibly shades the waiting area."
        ),
    },
    {
        "shade_source": "Incidental",
        "operational_definition": "A nearby building or other non-shelter built feature visibly shades the waiting area.",
    },
]

DEFAULT_COVERAGE_TAXONOMY = [
    {
        "name": "No Shade",
        "description": "No shade visibly reaches the waiting area.",
        "color": "#dc143c",
        "sort_order": 1,
    },
    {
        "name": "Limited Shade",
        "description": "Shade visibly covers part of the waiting area, but not most of it.",
        "color": "#d69e2e",
        "sort_order": 2,
    },
    {
        "name": "Significant Shade",
        "description": "Shade visibly covers most of the waiting area or seating area.",
        "color": "#228b22",
        "sort_order": 3,
    },
    {
        "name": "Needs Review",
        "description": "The stop needs imagery, review, or disagreement resolution.",
        "color": "#808080",
        "sort_order": 4,
    },
]

_COVERAGE_ALIASES = {
    "no shade": "No Shade",
    "limited": "Limited Shade",
    "limited shade": "Limited Shade",
    "limited natural shade": "Limited Shade",
    "significant": "Significant Shade",
    "significant shade": "Significant Shade",
    "significant natural shade": "Significant Shade",
    "needs review": "Needs Review",
    "unknown": "Needs Review",
}

_SOURCE_ALIASES = {
    "natural": "Natural",
    "natural shade": "Natural",
    "tree": "Natural",
    "trees": "Natural",
    "vegetation": "Natural",
    "purpose-built": "Purpose-built",
    "purpose built": "Purpose-built",
    "purpose-built shade": "Purpose-built",
    "constructed": "Purpose-built",
    "constructed shade": "Purpose-built",
    "intentional built": "Purpose-built",
    "intentional built shade": "Purpose-built",
    "intentional constructed": "Purpose-built",
    "shelter": "Purpose-built",
    "canopy": "Purpose-built",
    "incidental": "Incidental",
    "incidental shade": "Incidental",
    "manmade": "Incidental",
    "manmade shade": "Incidental",
    "incidental built": "Incidental",
    "incidental built shade": "Incidental",
    "building": "Incidental",
}

_LEGACY_COVERAGE_DESCRIPTIONS = {
    "Limited Shade": {
        "Vegetation shades part of the waiting area, but not most of it.",
        "Shade visibly reaches part of the waiting area, but not most of it.",
        "Shade visibly reaches part of the waiting area, but does not cover most of it.",
    },
    "Significant Shade": {
        "Vegetation visibly covers most of the waiting area or seating area.",
    },
}


def normalize_shade_coverage(value: Any, fallback: str = "Needs Review") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return _COVERAGE_ALIASES.get(text.lower(), fallback)


def normalize_shade_source(value: Any) -> str:
    return _SOURCE_ALIASES.get(str(value or "").strip().lower(), "")


def split_shade_sources(value: Any) -> list[str]:
    sources: list[str] = []
    for part in re.split(r"[;,|]", str(value or "")):
        normalized = normalize_shade_source(part)
        if normalized and normalized not in sources:
            sources.append(normalized)
    return sources


def infer_sources_from_legacy_category(value: Any) -> list[str]:
    text = str(value or "").strip().lower()
    sources: list[str] = []
    for candidate in SHADE_SOURCE_OPTIONS:
        normalized = normalize_shade_source(candidate)
        aliases = [alias for alias, target in _SOURCE_ALIASES.items() if target == normalized]
        if any(alias in text for alias in aliases) and normalized not in sources:
            sources.append(normalized)
    return sources


def normalize_coverage_taxonomy(taxonomy: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    configured: dict[str, tuple[int, dict[str, Any]]] = {}
    for item in taxonomy or []:
        original_name = str(item.get("name", "")).strip()
        normalized_name = normalize_shade_coverage(original_name, "")
        if not normalized_name:
            continue
        priority = 0 if original_name == normalized_name else 1
        existing = configured.get(normalized_name)
        if existing is None or priority < existing[0]:
            configured[normalized_name] = (priority, dict(item))

    normalized_taxonomy = copy.deepcopy(DEFAULT_COVERAGE_TAXONOMY)
    for default in normalized_taxonomy:
        existing = configured.get(default["name"])
        if not existing:
            continue
        configured_item = existing[1]
        for key in ["description", "color"]:
            configured_value = str(configured_item.get(key, "")).strip()
            if configured_value and not (
                key == "description"
                and configured_value in _LEGACY_COVERAGE_DESCRIPTIONS.get(default["name"], set())
            ):
                default[key] = configured_item[key]
    return normalized_taxonomy

