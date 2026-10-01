# Oko Sources

Declarative source manifests for **Oko Mobile** — anime, Asian drama, western movies/TV.
One file per site. No code, no keys, no app changes here. The app reads these later.

## Install

Have **Oko Mobile** installed? Tap to add the whole repo, or a single source
(opens the app and installs it — same as typing the repo in Settings → Content source):

[![Add repo](https://img.shields.io/badge/Add_repo-studionightloop%2Foko--source-blue)](oko://add-repo?repo=studionightloop%2Foko-source)

| Source | Install |
| --- | --- |
| AniKoto | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=anikoto) |
| AnimePahe | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=animepahe) |
| Re:Anime | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=reanime) |
| Miruro | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=miruro) |
| AnimeX | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=animex) |
| AniKage | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=anikage) |
| Lunar | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=lunar) |
| KissKH | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=kisskh) |
| ShuttleTV | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=shuttletv) |
| HydraHD | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=hydrahd) |
| Atlantic | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=atlantic) |
| Bingr | [Install](oko://add-repo?repo=studionightloop%2Foko-source&source=bingr) |

Manual: Oko → Settings → Content source → paste `studionightloop/oko-source` → Add.

## Sources (rank order preserved)

### Anime

| Rank | ID | Mirrors | Status |
| --- | --- | --- | --- |
| 1 | `anikoto` | `anikototv.to`, `anichi.to`, `anisuge.tv`, `animesogo.to`, `anixtv.me`, `animixplay.tube`, `animepahetv.to`, `9animez.org`, `hianimez.org` | active |
| 2 | `animepahe` | `animepahe.pw`, `animepahe.com`, `animepahe.org` | blocked (Cloudflare, needs session runner) |
| 3 | `reanime` | `reanime.to`, `reanime.cz`, `reanime.wtf` | active |
| 4 | `miruro` | `www.miruro.to`, `www.miruro.ru`, `www.miruro.bz`, `www.miruro.tv` | active |
| 5 | `animex` | `animex.one` | active |
| 6 | `anikage` | `anikage.cc` | active |
| 7 | `lunar` | `lunarx.to` | active |

### Drama

| Rank | ID | Mirrors | Status |
| --- | --- | --- | --- |
| 1 | `kisskh` | `kisskh.co`, `kisskh.la`, `kisskh.id`, `kisskh.is`, `kisskh.do`, `kisskh.ovh` | active |

### Western

| Rank | ID | Mirrors | Status |
| --- | --- | --- | --- |
| 1 | `shuttletv` | `shuttletv.su`, `shuttletv.pk` | active (user domains only) |
| 2 | `hydrahd` | `hydrahd.ws`, `hydrahd.com`, `hydrahd.me`, `hydrahd.ac` (`.ru` disabled) | active |
| 3 | `atlantic` | `atlantic.st` | observe |
| 4 | `bingr` | `bingr.one` | active |

Labels/enrichment: `everythingmoe.com` (anime ranks/tags), AniList/TMDB posters.

## Layout

```
sources/
  README.md
  VERSIONING.md        # bump rules + update popup flow
  schema-v1.json       # contract for *.oko.json
  registry.json        # ranked index: version/notes/hash/date per source
  Context.md           # tmp: how Oko UI consumes data (card/detail/CW/download)
  test.py              # health check, stdlib only
  anime/*.oko.json + *.CHANGELOG.md
  drama/*.oko.json + *.CHANGELOG.md
  western/*.oko.json + *.CHANGELOG.md
```

Manifest rules: `<id>.oko.json` with stable `id`, `category`, `rank`, `mirrors[]` in priority order,
`engine`, `capabilities`, ops `discovery/search/details/episodes/streams` as
`{request, response, extract}` mapping to `CircleFtpPost/Detail/Episode/FileInfo`
(see `Context.md`). JS/CF/kkey gaps go in `notes.blockers` + `confidence`, never faked.

## Use

```bash
python test.py                  # full: 64 checks (live + registry match)
python test.py --quick          # skip detail paths
python test.py --category anime|drama|western|meta
python test.py --json           # machine output
```

`test.py` checks mirrors, markers/JSON keys, `registry.version == manifest.version`,
`sha256` match, changelog entry. Exit 1 on any FAIL.

## Versioning

Semver per source: `PATCH` = fix, `MINOR` = new filter/capability, `MAJOR` = breaking.
Bump manifest `version` + top `*.CHANGELOG.md` + `registry.json` hash/notes/date.
App (later) diffs installed vs registry and shows
**"vOld → vNew, N changes — Update / Later / Skip"** (see `VERSIONING.md`).

## Security

No signing yet — plain JSON + `sha256` in registry verified by `test.py`.
Planned: offline Ed25519 sign `registry.json` + manifests, `publicKey` in app,
`allowedHosts`/https-only enforced on use. No secrets in git.

## Attribution

Source icons (`icons/*.png`, 192px) are from
[yuzono/anime-extensions](https://github.com/yuzono/anime-extensions)
(Apache-2.0) — same upstream whose extension model (per-source icon, base
URLs/mirrors, language, discovery/search/details/episodes/streams ops)
this repo mirrors in declarative JSON form. No code taken; manifests are
original Oko work.
