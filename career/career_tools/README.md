# tsu-vehicle-tools

Generate and inspect **Turbo Sliders Unlimited** vehicle files (`.veh`) without
the in-game editor or the Steam Workshop.

The format was reverse-engineered from ~120 workshop vehicles plus the game's
IL2CPP metadata (`global-metadata.dat`), which contains all the C# class and
field definitions (`TS.VehicleProperties`, `TS.CarPhysicsProperties`, and the
per-topic property classes). The parser/writer round-trips every current-format
sample **byte-identically** (all files written by game data versions ≥ 105, and
most back to ~91).

## Files

- `tsu_veh.py` — library: parse / write `properties.bin`, read / write `.veh`
  (a `.veh` is just a zip containing `properties.bin`). The full binary format
  is documented in this file's docstring.
- `make_veh.py` — CLI:
  - `python make_veh.py dump <file.veh>` — print any vehicle as a JSON spec
    (enums and tags shown by name)
  - `python make_veh.py build <spec.json> [-o out.veh] [--install]` — build a
    vehicle; `--install` copies it into the game's local `Vehicles` folder
    (`%USERPROFILE%\AppData\LocalLow\Turbo Sliders\Unlimited\<steamid>\Vehicles`)
    where it appears in-game as a local vehicle — no workshop upload needed.
    Values are validated against the game's min/max limits and enum tables;
    enum fields (modelId, engineSound, tags, combine modes, …) accept names
    or numbers. Strings are validated too: name non-empty and ≤ 40 chars,
    description ≤ 256, filename non-empty, ≤ 64, no characters that are
    illegal in file names.
  - `python make_veh.py schema [-o schema.json]` — machine-readable schema of
    every tunable parameter: type, default, min/max, the game's official
    tooltip text and all enum options. Built for driving a web tuning UI:
    render sliders/dropdowns from it, collect the values into a spec JSON,
    then call `build` (or use `tsu_veh`/`make_veh.from_spec` directly from
    Python) to produce the `.veh`.
- `test_roundtrip.py` — regression test against workshop + local samples.
- `PHYSICS_FIELDS.md` — field reference with defaults and min/max limits.
- `TOOLTIPS.md` — the game's official parameter descriptions (editor hover
  texts, extracted from the IL2CPP metadata) plus all dropdown enum values
  (models, engine sounds, tags, …). Raw data in `tooltips.json`.
- `merc_gt3.json` — example spec dumped from TraNin's Mercedes-AMG GT3 v5.
- `claude_gt3_test.json` — example modified spec.

## Workflow

```sh
# start from a car you like
python make_veh.py dump "path/to/some.veh" > mycar.json
# edit name/physics in mycar.json, then:
python make_veh.py build mycar.json --install
```

## Format summary

`properties.bin` (FormatId 111, FormatVersion 6, little-endian):

1. **Header** (fixed fields): format ids, writer game version, then the
   **vehicle guid** as two u64s which the game validates on load:
   `a = (ms since 2020-01-01 UTC) << 18 | 12 random bits << 6 | tag`
   (tag `0x0A` = player-made, `0x0B` = workshop item) and
   `b` = maker SteamID64 or workshop file id (must match the tag).
   The game displays guids as base32 `a-b` (alphabet `0-9` + consonant-ish
   letters). Then creation time as .NET ticks, 32-bit maker account id,
   5 flag bytes (the 5th = finalized), then a small bitmask-encoded byte
   section (bit 5 = game version at creation, currently 103).
   **No content checksum exists.**
2. **Strings** (u32 length + UTF-8): name, description, then u32 body-model id,
   then filename, maker name.
3. **Masked sections** — the core scheme: each section starts with one bitmask
   byte; for every set bit, the value of that field follows (float32 / byte /
   bool-byte / u16 / int32 enum, two bools ride in the mask itself). Clear bits
   mean "use the game default". Classes with > 8 fields use consecutive
   mask+values chunks.
   - Mid block: 3 misc sections (damage carries `maxHitPoints` u16), engine
     audio (3 chunks, first field = engine sample index u8), gear ratios
     (8 floats), gear audio.
   - Physics block, delimited by u16 markers `312 ... 313`
     (`CarPhysicsProperties.FormatId` / `FormatIdEnd`), version u16 = 3:
     sections `weight, speed, braking, steering, steering2, oversteering,
     sliding, spring, downforce, weightTransfer, gears, contact` — field lists
     and game defaults are in `tsu_veh.py`.

Field names come from the game's own IL2CPP metadata, so they match what the
in-game vehicle editor calls them (mass, maxSpeed, grip, downforce, …). A few
fields marked `x*`/`e*`/`s*` in the specs are serialized but their exact
meaning hasn't been pinned down yet; they're preserved verbatim on roundtrip.

## Notes / caveats

- Files written by old game builds (data version < ~91, plus a handful of
  odd ones) use older section layouts and are rejected with a clear error on
  `dump`; generation always targets the current layout.
- `modelId` picks the built-in chassis/body: observed 6=Countach, 8=formula,
  10=Mustang, 12=AMG GT3, 13=Ferrari 296. Custom 3D models are stored in
  separate workshop mesh files, not in `properties.bin`.
- Values are known-good in the ranges the in-game editor allows (metadata
  Min/Max constants are listed in `tsu_veh.py`); the game may clamp or reject
  values outside them.
