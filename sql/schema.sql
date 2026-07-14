-- Relational platform schema for Shade-GIS / Shade Study Builder.
-- The Streamlit builder uses a SQLite implementation of this shape by default;
-- this file is the Postgres-ready schema for shared deployments.

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  agency TEXT,
  region TEXT,
  description TEXT,
  owners TEXT,
  visibility TEXT NOT NULL DEFAULT 'Private' CHECK (visibility IN ('Public', 'Private')),
  dataset_version TEXT,
  methodology_version TEXT,
  source_name TEXT,
  source_license TEXT,
  source_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_settings (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  methodology_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  visualization_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  deployment_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shade_taxonomy (
  id BIGSERIAL PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  color TEXT,
  sort_order INTEGER NOT NULL DEFAULT 1,
  UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS stops (
  id BIGSERIAL PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  stop_id TEXT NOT NULL,
  stop_name TEXT NOT NULL,
  stop_lat DOUBLE PRECISION,
  stop_lon DOUBLE PRECISION,
  agency TEXT,
  routes TEXT,
  municipality TEXT,
  shading TEXT,
  shade_coverage TEXT,
  shade_sources TEXT,
  review_status TEXT,
  confidence DOUBLE PRECISION,
  ridership DOUBLE PRECISION,
  priority_score DOUBLE PRECISION,
  extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, stop_id)
);

-- Generated public apps can use this table in a shared PostgreSQL database.
-- It intentionally does not require a projects row because the voting store may be deployed alone.
CREATE TABLE IF NOT EXISTS shade_votes (
  id BIGSERIAL PRIMARY KEY,
  study_id TEXT NOT NULL,
  stop_id TEXT NOT NULL,
  voter_id TEXT NOT NULL,
  coverage_status TEXT NOT NULL,
  shade_sources TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (study_id, stop_id, voter_id)
);

CREATE TABLE IF NOT EXISTS images (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  stop_id TEXT,
  uri TEXT NOT NULL,
  storage_path TEXT,
  image_type TEXT,
  source TEXT,
  captured_at TIMESTAMPTZ,
  attribution TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shade_labels (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  stop_id TEXT NOT NULL,
  image_id TEXT REFERENCES images(id) ON DELETE SET NULL,
  labeler_id TEXT,
  labeler_role TEXT,
  shade_category TEXT,
  shade_coverage TEXT,
  shade_sources TEXT,
  confidence DOUBLE PRECISION,
  notes TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS review_history (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  stop_id TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  notes TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS releases (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  dataset_version TEXT,
  methodology_version TEXT,
  taxonomy_version TEXT,
  import_version TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
  released_at TIMESTAMPTZ,
  artifact_manifest_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, version)
);

CREATE TABLE IF NOT EXISTS import_logs (
  id BIGSERIAL PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source TEXT,
  format TEXT,
  rows INTEGER,
  imported_at TIMESTAMPTZ,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_stops_project ON stops(project_id);
CREATE INDEX IF NOT EXISTS idx_images_project_stop ON images(project_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_labels_project_stop ON shade_labels(project_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_review_project_stop ON review_history(project_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_releases_project ON releases(project_id);
