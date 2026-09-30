# Oko Sources — Versioning (v1)

Goal: user installs a source once. When we bump `version`, app shows:
**"New update for X — v0.1.0 → v0.2.0, N changes — Update / Later"** with changelog.

## 1. Rules

- Semver per source, independent: `MAJOR.MINOR.PATCH` (`pub_semver` in app).
  - `PATCH` (0.1.0→0.1.1): mirror swap, selector fix, timeout tweak. Auto-update safe.
  - `MINOR` (0.1.x→0.2.0): new capability/filter/field (e.g. shuttletv adds network filter). Popup, default Update.
  - `MAJOR` (x→1.0.0): breaking — `id` change, new auth (kkey/ticket), engine rewrite, episodes numbering change (breaks CW resume). Popup with `Breaking` badge + explicit confirm, never silent.
- `registry.json` is source of truth. Manifest `version` MUST equal registry `version`.
- `updatedAt`: `YYYY-MM-DD` of bump. `minAppVersion`: min Oko build that understands the manifest (e.g. streams-v2). Older apps hide update.
- `sha256`: of the manifest file bytes. App + `test.py` verify before offering update.
- `releaseNotes`: 1-line summary of THIS version (shown in popup). Full history in `<id>.CHANGELOG.md` next to manifest.

## 2. Bump flow (maintainer)

1. Edit `anime/<id>.oko.json`, bump `version`, write `releaseNotes` line.
2. Append entry on top of `anime/<id>.CHANGELOG.md` (`## vX.Y.Z — date` + bullets).
3. Run `sha256sum` → paste into `registry.json` entry (+ same version/notes/date).
4. `python test.py` must pass (includes version+hash match check).
5. Commit. App sees new registry on next check.

## 3. App check flow (to implement later, NOT now)

- Installed store (SharedPrefs): `{id: {version, addedAt, skippedVersion?}}`.
- Triggers: Sources screen open + daily background + pull-to-refresh. `GET registry.json` (ETag cache).
- For each installed `id`: if `semver(registry.version) > installed` and `appVersion >= minAppVersion` → update item:
  - Popup/bottom-sheet: icon, name, `vOld → vNew`, `MAJOR? Breaking badge`, bullets = changelog entries between old..new, `[Update] [Later] [Skip this version]`.
  - `Later` = dismiss until next check. `Skip` = set `skippedVersion=new`, don't ask again for that version.
- Apply: download manifest → verify `sha256` (+ signature when added) → replace stored copy → keep `id` stable so CW/downloads resume → toast `X updated`.
- Rank/status changes (no version bump): show silently as row reorder, no popup.

## 4. Files

- `registry.json`: `categories.{anime,drama,western}[]` entries with `version/releaseNotes/updatedAt/minAppVersion/sha256`.
- `*/<id>.CHANGELOG.md`: newest-first history, popup bullets come from here.
- `test.py`: `meta-versions` check — registry.version == manifest.version and sha256 matches file.
