-- Online levels. Apply with:
--   npx wrangler d1 execute fun-ball-game --remote --file=schema.sql
CREATE TABLE IF NOT EXISTS levels (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  author TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  theme TEXT NOT NULL DEFAULT 'Midnight',
  blocks INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL,
  created INTEGER NOT NULL,
  likes INTEGER NOT NULL DEFAULT 0,
  plays INTEGER NOT NULL DEFAULT 0,
  token_hash TEXT NOT NULL,
  ip_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS levels_created ON levels (created DESC);
CREATE INDEX IF NOT EXISTS levels_top ON levels (likes DESC, plays DESC);
CREATE INDEX IF NOT EXISTS levels_ip ON levels (ip_hash, created);

CREATE TABLE IF NOT EXISTS likes (
  level_id TEXT NOT NULL,
  ip_hash TEXT NOT NULL,
  PRIMARY KEY (level_id, ip_hash)
);
