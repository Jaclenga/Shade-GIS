-- Schema for Tampa Shade app

CREATE TABLE IF NOT EXISTS stops (
  stop_id TEXT PRIMARY KEY,
  stop_code TEXT,
  stop_name TEXT,
  stop_lat DOUBLE PRECISION,
  stop_lon DOUBLE PRECISION,
  shading TEXT DEFAULT 'Unknown' CHECK (shading IN ('Unknown', 'No Shade', 'Natural Shade', 'Manmade Shade'))
);

CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS votes (
  id SERIAL PRIMARY KEY,
  stop_id TEXT REFERENCES stops(stop_id),
  username TEXT REFERENCES users(username),
  vote TEXT CHECK (vote IN ('Shaded', 'No Shade')),
  ts TIMESTAMP DEFAULT now(),
  UNIQUE (stop_id, username)
);
