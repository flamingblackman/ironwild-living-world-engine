# Companion integration — discovery (Phase 2 item 4)

Discovery done 2026-11-21. Read-only: no app file was changed, no
app.db query was run. The build waits on the hub (see §5).

## 1. What the app is

Private TypeScript space, slug `campaign-companion`, built Oct 27
2026 (`~/workspace/ts-spaces/campaign-companion`). Three universes
only (Ironwild, Ashen Accord, Veldt City). Private play version, NOT
IP-sanitized, NOT cleared for sale. Reference data (universe bibles,
combat codexes, the 87-entry mechanic registry, Multiverse Law) is a
build-time parsed JSON snapshot of the user's own workspace files,
served read-only by `getReference`. Live campaign state lives in
`app.db` and is user-owned.

## 2. House rules (the app's AGENTS.md — they bind the Engine too)

- Build, audit, and ship only through the web-artifact tools (the
  builder). Do NOT hand-edit the built bundle, do NOT `bun run
  build`. The main agent must NOT build from the directory — it
  requests a change by describing the edit, which spawns a builder.
- **Do NOT run sqlite or scripts against `app.db`.** The Engine
  NEVER writes `app.db` directly (already the Phase 2 plan; the
  app's own rules agree).
- No named owner recorded — **app changes are a hub question.**

## 3. Data model (server/src/schema.ts + actions.ts)

Four tables in `app.db`:

- `campaigns` — id (`ironwild` | `ashen-accord` | `veldt-city`),
  name, stateLabel, versionMajor/Minor, scene, tension, notes,
  updatedAt.
- `characters` — campaignId, name, role, machineName, fieldsJson
  (Array<{label, value}> — the editable sheet rows).
- `clocks` — campaignId, name, kind (`clock` | `faction` |
  `status`), current, max, status, note, sort.
- `decisions` — campaignId (unique), text, optionsJson.

Actions (server/src/actions.ts): `getReference` (read-only),
`getState` (reads all campaigns; seeds once from the pipeline clock
ledgers when the tables are empty), `updateCampaign`,
`updateCharacter`, `saveClock`, `deleteClock`, `updateDecision`.
Every mutation goes through these actions (with
`ctx.invalidateQueries()`). The client (App.tsx, 1503 lines) has
five tabs: state, world, codex, mechanics, handshake. The "world"
tab is the bible (reference data), NOT a live world view. The
"state" tab is the `app.db` campaign state. The handshake generator
builds a handshake from the campaign state + selected mechanics
(8-tuple / 350-token cap).

## 4. The integration shape (Phase 2 plan, confirmed by discovery)

- The Engine writes a stable JSON export, `runs/<world>/world-view.json`,
  from the engine DB (world, tick, clocks, Bonds/statuses, resources,
  locations, pending decision, recent events).
- The app reads it through its own actions: a NEW import/refresh
  action that maps the export into the campaign state via the
  EXISTING update actions (`updateCampaign` for scene/tension/
  version, `saveClock` for clocks, `updateCharacter` for the sheet,
  `updateDecision` for the pending decision). No direct DB writes,
  no new write path.
- The client gains a world-view section (or the state tab is fed
  from the engine export) — a builder decision, not an Engine one.

## 5. What's missing, and what waits on the hub

**Engine side (Engine work, no hub call needed):** the export does
not exist yet. `src/render.py` produces static HTML
(`world-view.html`), not a `world-view.json`. The export is a new
render mode (or `render --format json`) that writes
`runs/<world>/world-view.json` alongside the HTML.

**App side (builder work, hub approval needed):** the new
import/refresh action + the client section. That is a change to the
app, so it goes through the artifact builder after the hub approves
it — the Engine does not build it.

**Open question (hub, not Engine): which world feeds the app
first?** The LIVE Ironwild campaign (waits on Bryan resolving Turn
136; no live engine DB exists yet) or the Fork A test world (the
only live engine DB)? The engine-side export is the same either
way; the app-side mapping is the same; the choice is which DB feeds
it. Related: the app's Ironwild campaign is currently seeded from
the old pipeline clock ledgers (Bond 5/5, Turn 131-era live state),
and the app's rule is that after seeding, the user's in-app edits
are authoritative and code never rewrites them — so the import must
be an explicit user action (a button), never a silent overwrite.
That is a design point for the builder.

## 6. Status

Discovery DONE (this doc). Next: (a) Engine writes the
world-view.json export; (b) hub approves the app change + names
which world feeds it; (c) builder adds the import action + client
section. No seed change. Fork A stays at v1.6. Freeze intact.

## 7. Decided plan (Bryan, 2026-11-21 13:24 EST)

Bryan decided: **feed the app the LIVE world campaign that will be
taking place on ChatGPT. Import button APPROVED.** The plan, stated
plainly:

- **Built now:** the Engine's world-view.json export — DONE
  2026-11-21 (`src/render.py: render_world_view_json`,
  `render --format json [--carried <carried.json>]`, stable path
  `runs/<world>/world-view.json`; 3 new tests in
  `tests/test_render.py`; suite 146 pass). Proven against the live
  Fork A test DB as the mechanism test: tick 12, last_swept 135
  ForkA-vFINAL.4, scene/tension from the carried record, clocks
  and engines matching the DB, 20 recent events, 7 locations, 28
  resource rows.
- **Next:** the app's import action + button (builder work — the
  Engine requests it by describing the edit, per the app's
  AGENTS.md; the Engine does not build from the app directory and
  never writes app.db). The action reads the export and maps it
  into the campaign state via the existing update actions
  (updateCampaign, saveClock, updateCharacter, updateDecision),
  as an explicit user action (a button), never a silent overwrite.
- **Waits on the live seed:** the live feed itself. The import can
  only feed the app's Ironwild campaign from a live engine DB once
  one exists — that needs Bryan resolving the live Turn 136, then
  Lore seeding the live world. Until then there is no live export
  to import.
- **Fork A as a stand-in: NOT AT ALL.** Fork A is used only to
  prove the export/import mechanism on scratch. The app's
  Ironwild campaign never receives Fork A state — Fork A is a
  parallel test timeline and nothing transfers back to live canon.
  The app's Ironwild campaign keeps its live seed (the pipeline
  clock ledgers) until the live engine DB exists.

No seed change. Fork A stays at v1.6. Freeze intact.
