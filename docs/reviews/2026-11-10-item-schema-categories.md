# Item category and schema audit — 2026-11-10

This is a read-only audit of candidate 24. No data, application, renderer,
parser, fitting, splitting or grouping implementation changes are included.

`tools/verify_item_schema_categories.py` checks 329 records and 570 fields.
Fifty-one type fields overlap the ordinary weapon/armor check, so this adds
519 fields to the consolidated report, now 3,209 with zero confirmed metadata
differences. This total includes authored compatibility identifiers and the
previous 177 authored provenance objects; it is neither a count of printed
game rules nor a whole-record or whole-SRD fidelity certificate.

The independent printed inventory supplies all 236 ordinary equipment,
poison and trinket entities: 94 base items, 136 items and six groups. Physical
source grids, section boundaries and inline variant lists select categories.
The four Gaming Set and ten Musical Instrument variants are inline lists,
not tables. The musical list crosses columns at the printed `dul-` / `cimer`
word break, which has one explicit reviewed source-layout join.

The retained `rarity: "none"` is an index of **no magic-item rarity assigned in
that source scope**. It does not assert that an object is nonmagical. The
Generic Variant code identifies a collection wrapper; the underlying printed
weapon/armor restrictions remain a separate gate. Hat of Many Spells' focus
index and the five magical horns' instrument/base-Horn relations are authored
usage/physical indexes, retaining the printed Wondrous Item classification.
They do not establish mundane prices, weights, proficiency grants or powers.
The 25 type and nine property abbreviations are authored schema identifiers.

The importer requires the complete four-file hash inventory, official PDF hash,
current family model, exact identities and per-record fields, strict typed
actual/value/source-expectation consistency, and matching source scopes. It
reconstructs the source expectations independently and repeats the audit's
exclusions before accepting a stored proof. Updated hashes alone cannot make
an unbound `rarity: "none"` on a magic item acceptable.

Independent review found and rechecked three fixes in this audit tooling:

- Same-count replacement of Two-Handed with duplicate Heavy evidence is now
  rejected by the independent complete property-meaning/code inventory.
- PDF coordinate tuples normalize to JSON arrays at the evidence boundary,
  so persisted proofs compare to fresh extraction without weakening strict
  comparison of game/schema values.
- Proof imports repeat exclusions as well as positive facts; a forged fresh
  hash inventory cannot bypass an out-of-scope absent-rarity value.

The reviewer accepted the current saved proof's 329 records and rejected the
reproduced corruptions, with no remaining findings in this scoped review.

Evidence under the desktop checkout's `output/srd-fork/`:

- `candidate-24-schema-category-review/verification.json`: source inventory,
  full physical evidence, classifications, current inputs and verified fields.
- `candidate-24-schema-item-review/review.json` and its
  `remaining-field-inventory.json`: consolidated results and explicit remaining
  metadata, including generic restrictions, group/reference links and packs.
- `candidate-24-schema-boundary-proof.json`: current unchanged candidate,
  installed data and protected-code fingerprints; existing exact full-output
  captures and final PDF certificate are reused, not freshly rendered.
- `candidate-24-schema-source-tests.log`: the complete source-suite run.

The complete suite passes **148 tests with zero skips**, including all ten
new category/schema tests and the actual positive/negative CLI import checks.

Full-database renderer acceptance remains exact on **both** platforms: 12,270
cards, 10,183 entries and 1,374 sheets, with ordered card markup, split
boundaries, shell and whole HTML equal to each platform's frozen baseline.
The six separately approved SRD portrait overrides remain the only permitted
SRD count change (1,610 to 1,616). No baseline may be regenerated to absorb a
regression. Native-device, real default-download, remaining source/consumer
and publication gates remain open.
