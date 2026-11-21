-- Living World Engine — state schema (Phase 1)
-- One SQLite database per world fork. This file is the single source of truth
-- for what the world IS. The event log (events) is append-only: enforced by
-- triggers below AND by a hash chain (see src/events.py).
-- The engine never writes to canon files (bibles, codices, registry, gems).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS npcs (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    faction_id   TEXT REFERENCES factions(id),
    location_id  TEXT REFERENCES locations(id),
    age          INTEGER,                     -- null when canon gives no age
    status       TEXT NOT NULL DEFAULT 'active',  -- active | active, under guard | active, watched | retired | dead
    goals        TEXT NOT NULL DEFAULT '[]',      -- JSON list of goal sentences/tags
    capabilities TEXT NOT NULL DEFAULT '[]',      -- JSON list of capability ids
    successor    TEXT REFERENCES npcs(id)          -- named successor (LR-03)
);

CREATE TABLE IF NOT EXISTS engines (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    shape           TEXT NOT NULL,  -- Stalker | Bulwark | Skytalon | Deepmaw (Lore maps others onto these)
    pilot_id        TEXT REFERENCES npcs(id),
    location_id     TEXT REFERENCES locations(id),  -- where the Engine is; the Pack's Engines start together
    hunger          INTEGER NOT NULL DEFAULT 0,   -- 0..10
    hunger_type     TEXT NOT NULL,  -- speed | territory | wreckage | clean_fight | hunt | protective
    hunger_threshold INTEGER NOT NULL DEFAULT 7,
    molt_trigger    INTEGER NOT NULL DEFAULT 0,   -- 1 when an earned, unspent Molt trigger exists (LR-02)
    status          TEXT NOT NULL DEFAULT 'active' -- active | field-patched | exhausted | damaged | netted | molted | dead
    -- Bond lives ONLY in the bonds table, never here.
);

-- One Bond row per Engine. pilot_id is NULL when the Engine answers to the
-- Pack collectively (no pilot assigned in canon); the engine must never
-- assign a pilot without Lore approval.
CREATE TABLE IF NOT EXISTS bonds (
    engine_id TEXT PRIMARY KEY REFERENCES engines(id),
    pilot_id  TEXT REFERENCES npcs(id),
    bond      INTEGER NOT NULL DEFAULT 0 CHECK (bond BETWEEN 0 AND 5)
);

CREATE TABLE IF NOT EXISTS factions (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    doctrine  TEXT NOT NULL DEFAULT '',
    standings TEXT NOT NULL DEFAULT '{}'  -- JSON: {other_faction_id: standing word or number}
);

CREATE TABLE IF NOT EXISTS locations (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    kind                  TEXT NOT NULL,  -- caravan | den | nest | wreck | region | city
    controller_faction_id TEXT REFERENCES factions(id),
    status                TEXT NOT NULL DEFAULT 'standing', -- standing | intact | damaged | contested | unmapped | fortified | fallen | destroyed
    mapped                INTEGER NOT NULL DEFAULT 1,      -- 0 = unmapped (scout/dream_share reveal it)
    condition             TEXT                               -- free text, e.g. siege-scarred
    -- Territory changes are recorded here AND as events (with old and new
    -- values), so a future dynamic map (Phase 4) can render flips, falls,
    -- and destruction from state alone. Locations are never deleted.
);

CREATE TABLE IF NOT EXISTS resources (
    holder_id   TEXT NOT NULL,
    holder_kind TEXT NOT NULL,  -- npc | engine | faction | location | pack
    resource    TEXT NOT NULL,  -- Salvage | Feed | Cores | Territory
    qty         INTEGER NOT NULL DEFAULT 0 CHECK (qty >= 0),
    PRIMARY KEY (holder_id, holder_kind, resource)
);

CREATE TABLE IF NOT EXISTS clocks (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    value       INTEGER NOT NULL DEFAULT 0 CHECK (value >= 0),
    max         INTEGER NOT NULL CHECK (max > 0),
    status      TEXT NOT NULL DEFAULT 'running', -- running | complete
    on_complete TEXT NOT NULL DEFAULT '[]'       -- JSON list of effect ops (see src/actions.py)
);

-- Append-only event log. No UPDATE or DELETE, ever. A correction is a new event.
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tick       INTEGER NOT NULL,
    actor_id   TEXT NOT NULL,
    action     TEXT NOT NULL,
    score      REAL,
    runner_up  TEXT,              -- "action:score" of the second-best option, or null
    effect     TEXT NOT NULL,     -- JSON list of applied effect ops
    prev_hash  TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS eras (
    id              INTEGER PRIMARY KEY,
    name            TEXT,               -- null when Lore has not named the era; the engine never names eras
    start_tick      INTEGER NOT NULL,
    end_tick        INTEGER,          -- null while the era is current
    legacy_applied  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS snapshots (
    tick         INTEGER PRIMARY KEY,
    state_sha256 TEXT NOT NULL
);

-- Per-tick flags (patrolled locations, raids in progress, rested actors,
-- merged pairs). Set during a tick, cleared at the start of the next tick.
CREATE TABLE IF NOT EXISTS tick_flags (
    flag  TEXT PRIMARY KEY,
    tick  INTEGER NOT NULL,
    value TEXT NOT NULL DEFAULT ''
);

-- Append-only enforcement at the database level. These triggers refuse any
-- UPDATE or DELETE on events, even from the engine itself.
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;
