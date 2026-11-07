-- The license server's own database (Cloudflare D1). Not the case database: Mabillon's case
-- tables live only in core/schema.sql, and nothing here ever holds case data.
-- Apply with: npx wrangler d1 execute mabillon-license --remote --file workers/license/schema.sql

-- One row per license. Added by the Mabillon team (README.md); there is no self-serve sign-up.
CREATE TABLE IF NOT EXISTS licenses (
  id TEXT PRIMARY KEY,                -- lic_<letters and digits>
  email TEXT NOT NULL UNIQUE,         -- lower case
  plan TEXT NOT NULL,                 -- pilot, standard, ...
  paid_through TEXT NOT NULL,         -- ISO 8601 UTC; the license's "expires"
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
  created_at TEXT NOT NULL
);

-- A sign-in link we emailed: good for 15 minutes, once. Only its SHA-256 is kept.
CREATE TABLE IF NOT EXISTS links (
  hash TEXT PRIMARY KEY,
  license_id TEXT NOT NULL REFERENCES licenses(id),
  state TEXT NOT NULL,
  challenge TEXT NOT NULL,
  return_to TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

-- The one-time code the browser carries back to the app: good for 5 minutes, once.
CREATE TABLE IF NOT EXISTS codes (
  hash TEXT PRIMARY KEY,
  license_id TEXT NOT NULL REFERENCES licenses(id),
  challenge TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

-- A signed-in computer: the SHA-256 of its sign-in token, when it last renewed and with which
-- Mabillon version. Nothing else about the computer.
CREATE TABLE IF NOT EXISTS tokens (
  hash TEXT PRIMARY KEY,
  license_id TEXT NOT NULL REFERENCES licenses(id),
  created_at TEXT NOT NULL,
  last_renewed_at TEXT NOT NULL,
  app_version TEXT NOT NULL
);
