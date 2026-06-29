# Shade Study Platform Schema

This document describes the MVP schema implemented by the Streamlit builder and the broader entities the repository is moving toward.

## Project

Each study is configured as a project.

| Field | Purpose |
| --- | --- |
| `name` | Public project name. |
| `agency` | Transit agency or agencies represented in the dataset. |
| `region` | City, county, metro area, or study geography. |
| `description` | Short project description. |
| `owners` | People or organizations responsible for the project. |
| `visibility` | Public or private publication status. |
| `dataset_version` | Version of the current stop and shade dataset. |
| `methodology_version` | Version of the current assessment method. |
| `source_name` | Primary transit dataset or source label. |
| `source_license` | License or terms for the source data. |
| `source_url` | Source URL when available. |

## Bus Stops

The builder accepts GTFS-compatible stops and mapped CSV files.

Required fields:

| Field | Purpose |
| --- | --- |
| `stop_id` | Unique stop identifier. |
| `stop_name` | Human-readable stop name. |
| `stop_lat` | Latitude in WGS84. |
| `stop_lon` | Longitude in WGS84. |

Optional fields:

| Field | Purpose |
| --- | --- |
| `agency` | Agency label for multi-agency studies. |
| `routes` | Semicolon-separated route labels serving the stop. |
| `municipality` | Local jurisdiction or neighborhood label. |
| `shading` | Current shade taxonomy category. |
| `shade_coverage` | Coverage dimension, if collected separately. |
| `shade_sources` | Source dimension, such as natural or built shade. |
| `review_status` | Workflow status such as unlabeled, accepted, or disputed. |
| `confidence` | Reviewer or model confidence. |
| `ridership` | Ridership measure used for prioritization. |
| `heat_vulnerability_index` | Heat exposure or vulnerability score. |
| `heat_vulnerability_label` | Human-readable heat vulnerability category. |
| `tree_canopy_pct` | Nearby tree canopy share from 0 to 1. |
| `lst_median` | Median land surface temperature or equivalent heat metric. |

## Shade Taxonomy

The default reusable taxonomy is:

| Category | Intent |
| --- | --- |
| `No Shade` | No shade reaches the waiting area. |
| `Limited Natural Shade` | Vegetation shades part of the waiting area. |
| `Significant Natural Shade` | Vegetation shades most of the waiting area. |
| `Intentional Built Shade` | A shelter, canopy, awning, or similar passenger facility shades riders. |
| `Incidental Built Shade` | A nearby non-shelter built feature shades riders. |
| `Needs Review` | The stop needs imagery, review, or disagreement resolution. |

Project teams can edit names, descriptions, colors, and sort order in the `Data` page.

Visualization settings store the selected map color field, premade and editable palettes for shade
categories, review statuses, priority-score gradients, and other categorical columns, plus marker
shape, size, opacity, outline, base map style, overlay selections, dashboard cards, and priority
weights. The builder presents those settings in an expandable, scrollable panel beside the live map
preview.

## Preview Exports

The `Preview` page currently exports:

- Stops CSV.
- Stops GeoJSON.
- Study configuration JSON containing project metadata, taxonomy, methodology copy, visualization settings, and import log.

The public preview also includes a user-facing toggle to show or hide stops whose shade label is
still `Needs Review` without changing the exported dataset.

## Future Entities

The issue roadmap points to these additional entities:

- `Image`: uploaded field photos, Street View references, Mapillary images, or satellite screenshots.
- `ShadeLabel`: every expert, crowd, imported, or model-assisted label submission.
- `PriorityScore`: score, component values, and formula version.
- `Release`: dataset version, methodology version, taxonomy version, import version, release date, source revisions, and download artifacts.
