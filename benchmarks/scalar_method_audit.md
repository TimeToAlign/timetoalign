# Scalar Method Audit (WP2 → WP3 hand-off)

This audit walks every method on the WP2-migrated scalars and classifies
it as **data-shaped** or **behavior-shaped** per the diagnostic from
``workshop_typing_push.md``:

> *if I had a million of these, would I want this method to run on
> each one?*

* **data-shaped** → must exist as a ``pa.compute`` expression at the
  ``SemanticField[T]`` level under WP3.  ``needs_field_mirror = yes``.
* **behavior-shaped** → runs on a single materialised scalar at a system
  edge (display, comparison with `__eq__`, construction).  No field
  mirror needed.

Per-scalar instance dunders (``__init__``, ``__repr__``, ``__str__``,
``__hash__``, ``__float__``, ``__int__``, ``__index__``, ``__add__``,
``__sub__``, …) are listed once at the bottom — their classification is
uniform across scalars.

| scalar | method | classification | needs_field_mirror? | notes |
|---|---|---|---|---|
| Coordinate | `to_float` | data-shaped | yes | `pc.cast(arr.value, pa.float64())` |
| Coordinate | `to_int` (truncate/round/floor/ceil) | data-shaped | yes | `pc.trunc/floor/ceil/round` |
| Coordinate | `to_fraction` | behavior-shaped | no | per-row Fraction (Python-only) |
| Coordinate | `is_zero` / `is_positive` / `is_negative` | data-shaped | yes | `pc.equal(arr.value, 0)` etc. |
| Coordinate | `with_value` / `with_unit` / `with_timeline` | behavior-shaped | no | copy-on-write, runs at edges |
| Coordinate | `domain` | behavior-shaped | no | derived from unit (one-time on field) |
| Coordinate | `number_type` | behavior-shaped | no | derived from value-type, one-time |
| Coordinate | `metadata_dict` | behavior-shaped | no | scalar→pa.Field encoding |
| Duration | `to_float` / `to_int` / `to_fraction` | data-shaped | yes | identical to Coordinate |
| Duration | `is_zero` | data-shaped | yes | |
| Duration | comparisons (`<`/`<=`/`>`/`>=`) | data-shaped | yes | `pc.less` etc. |
| Duration | `metadata_dict` | behavior-shaped | no | |
| EnharmonicPitchClass | `to(EnharmonicPitchClass)` | data-shaped (identity) | no | trivial passthrough |
| EnharmonicPitchClass | `get` | data-shaped | yes | `pc.cast(arr.pitch_class, pa.string())` |
| EnharmonicPitchClass | `from_row` | behavior-shaped | no | per-row at trust boundary |
| EnharmonicPitchClass | `to_dict` | behavior-shaped | no | bulk path uses column-builder |
| EnharmonicPitchClass | `__eq__` accepting int | behavior-shaped | no | scalar comparison sugar |
| GenericPitchClass | `to(GenericPitchClass)` | data-shaped (identity) | no | |
| GenericPitchClass | `get` | data-shaped | yes | indexed lookup by step |
| GenericPitchClass | `from_row` / `to_dict` | behavior-shaped | no | |
| GenericPitch | `to(GenericPitchClass)` | data-shaped | yes | drop octave column |
| GenericPitch | `get` | data-shaped | yes | string concat step+octave |
| GenericPitch | `from_row` / `to_dict` | behavior-shaped | no | |
| SpecificPitchClass | `to(EnharmonicPitchClass)` | data-shaped | yes | `pc.add_mod(step_semi[arr.step], arr.alter, 12)` |
| SpecificPitchClass | `get` | data-shaped | yes | accidental string concat |
| SpecificPitchClass | `pitch_class` (@property) | data-shaped | yes | `pc.mod(pc.add(step_semi[step], alter), 12)` |
| SpecificPitchClass | `fifths` (@computed_field) | data-shaped | yes | base_fifths[step] + 7*alter |
| SpecificPitchClass | `from_label` / `from_row` / `to_dict` | behavior-shaped | no | |
| EnharmonicPitch | `to(MidiPitch)` | data-shaped | yes | metadata-only retype |
| EnharmonicPitch | `to(EnharmonicPitchClass)` | data-shaped | yes | `pc.mod(arr.midi_number, 12)` |
| EnharmonicPitch | `get` | data-shaped | yes | label + octave concat |
| EnharmonicPitch | `pitch_class` (@property) | data-shaped | yes | `pc.mod(arr.midi_number, 12)` |
| EnharmonicPitch | `octave` (@property) | data-shaped | yes | `pc.subtract(pc.divide(arr.midi_number, 12), 1)` |
| EnharmonicPitch | `from_row` / `to_dict` | behavior-shaped | no | |
| MidiPitch | `get` (default format `"midi"`) | data-shaped | yes | string cast |
| SpecificPitch | `to(*)` (full matrix) | data-shaped | yes | column-wise mirror in WP3 |
| SpecificPitch | `get` | data-shaped | yes | accidental + octave concat |
| SpecificPitch | `pitch_class` (@property) | data-shaped | yes | |
| SpecificPitch | `midi_number` (@property) | data-shaped | yes | `(octave+1)*12 + base[step] + alter` |
| SpecificPitch | `fifths` (@computed_field) | data-shaped | yes | |
| SpecificPitch | `from_label` / `from_row` / `to_dict` | behavior-shaped | no | |
| HarmonyLabel | `from_row` / `to_dict` | behavior-shaped | no | |
| HarmonyLabel | `metadata_dict` | behavior-shaped | no | |
| PitchBasedHarmony | `from_row` / `to_dict` | behavior-shaped | no | |
| WesternTertianHarmony | `from_row` / `to_dict` | behavior-shaped | no | |
| RomanNumeralHarmony | `from_row` / `to_dict` | behavior-shaped | no | |
| DcmlHarmony | `from_label` (full DCML parse) | behavior-shaped | no | regex + ms3 lookup; per-row only |
| DcmlHarmony | `from_row` / `to_dict` | behavior-shaped | no | |
| DcmlHarmony | `metadata_dict` | behavior-shaped | no | |
| Note | `is_rest` (@property) | data-shaped | yes | `pc.is_null(arr.midi_pitch) & pc.is_null(arr.specific_pitch)` |
| Note | `from_row` / `to_dict` | behavior-shaped | no | columnar separation lives outside |
| Measure | `metadata_dict` | behavior-shaped | no | one-time per field |
| Measure | `from_row` / `to_dict` | behavior-shaped | no | |

## Per-scalar instance dunders — uniform classification

| dunder | classification | rationale |
|---|---|---|
| `__init__` (positional shim) | behavior-shaped | edge construction |
| `__repr__` / `__str__` | behavior-shaped | edge display |
| `__hash__` | behavior-shaped | edge identity (rarely bulk) |
| `__eq__` (incl. int-accepting variants) | data-shaped | bulk equality via `pc.equal` |
| `__lt__` / `__le__` / `__gt__` / `__ge__` | data-shaped | bulk compare |
| `__add__` / `__sub__` / `__mul__` / `__truediv__` / `__floordiv__` (Coordinate) | data-shaped | bulk arithmetic via `pc` |
| `__float__` / `__int__` / `__index__` | behavior-shaped | scalar coercion at edge |

## Summary

* **data-shaped methods needing field mirrors (WP3 input):** 37
* **behavior-shaped methods (pydantic-only):** 42

The data-shaped column drives WP3's ``SemanticField[T]`` API: each entry
becomes a ``field.<method>()`` returning a ``SemanticField[U]`` for
conversions or a ``pa.Array`` for derivations, implemented as a
``pa.compute`` expression over the underlying column.  Parity tests
compare the result of ``[scalar.method() for scalar in materialised]``
against ``field.method()`` element-wise, on both full fields and slices.
