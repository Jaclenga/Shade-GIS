# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this repository is currently in a
pre-release phase while the reusable platform stabilizes.

## [Unreleased]

### Added
- Configurable public bus-stop coverage voting in generated apps, including editable admin controls,
  per-browser-session vote handling, consensus thresholds, SQLite development storage, and optional
  shared PostgreSQL persistence for hosted deployments, managed from a dedicated builder page.
- Canonical separation of shade coverage (`No Shade`, `Limited Shade`, `Significant Shade`) from
  shade sources (`Natural`, `Constructed`, `Manmade`) across imports, labeling, voting, maps, and exports.
- Public voting now mirrors raw labeling with a separate multi-checkbox shade-source assessment
  persisted alongside each coverage vote.
- Public contributor guidance in `CONTRIBUTING.md`.
- Support expectations in `SUPPORT.md`.
- Governance and maintainer decision guidance in `GOVERNANCE.md`.
- Automated test and CI documentation in `README.md`.

## [0.1.0] - 2026-07-01

### Added
- Reusable Shade Study Builder workflow for importing GTFS, CSV, GeoJSON,
  zipped Shapefile, API-hosted, and manual stop data.
- Multi-project local SQLite storage with schema notes for shared Postgres
  deployments.
- Public preview app generation, export tools, raw labeling workflow, admin
  review tools, and visualization controls.
- Pytest coverage for storage, imports, labels, exports, scoring, smoke tests,
  and Playwright-based UI coverage in CI.
