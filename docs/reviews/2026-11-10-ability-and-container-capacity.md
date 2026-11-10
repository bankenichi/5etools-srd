# Ability and container-capacity source checks — 2026-11-10

Candidate 23 changes only unused `containerCapacity` metadata on eleven SRD
item records. All 28 generated desktop/Android HTML files are byte-identical
to candidate 22. Each platform retains 1,616 cards / 1,488 entries, with the
same grouping, splits, order and layout. Neither app renderer, parser, fitting,
splitting or grouping implementation changed. The 38 protected code hashes and
651 installed full-database JSON hashes still match their frozen baselines.

## Independent source checks

`tools/verify_item_abilities.py` freshly re-proves the saved family models
against the pinned official PDF. Giant identity selects the printed score row;
candidate numerical values never select an answer. All 30 existing ability
query fields match their source effects. The evidence retains wearing and
attunement requirements, the higher-existing-score exceptions, the potion's
one-hour duration, study requirements, score maxima and the particular Star
card effect. These are query indexes of available effects, not complete or
unconditional grants; the complete printed rules remain in each item's prose.

`tools/verify_item_capacities.py` reconstructs nineteen source scopes directly
from physical PDF glyphs. Thirteen retained capacity objects match exact source
facts, six unsupported objects are required to be absent, and eleven item UID
references resolve uniquely inside this SRD projection. Compartments retain
their order and limits; alternatives within a compartment are not additive.
Literal text retains the additional volume limits even when the query object
indexes only weight. `weightless` indexes contents exempt from ordinary added
load; it does not make a container weight zero. Efficient Quiver's printed
two-pound upper bound is explicitly distinguished from a fixed weight.

The final consolidated item audit covers 730 records and 2,401 enumerated
verified metadata fields, with zero confirmed differences. No ability or
container-capacity field remains in that report's unproved inventory. Other
metadata, typography, schema and omission gates remain incomplete; this is
not a whole-record or whole-SRD fidelity certificate.

## Exactly eleven data corrections

The preconditioned policy is `corrections/zzzzzz-item-capacities.json`.

- Flask, Glass Bottle, Iron Pot, Jug and Waterskin lose rounded cubic-foot
  conversions. Their exact printed pint/gallon capacities remain in prose.
- Vial loses an assumed pound conversion of the unqualified printed ounces;
  the exact source quantity remains in prose.
- Pouch retains its printed six-pound capacity and loses unprinted ammunition
  quantities.
- Crossbow Bolt Case, Map or Scroll Case, Quiver and Efficient Quiver retain
  all printed limits while eleven foreign `|xphb` references become resolving
  `|srd521` references.

All other fields of those eleven records are exactly equal. The other 39 data
files are byte-identical. All 2,136 citation queries were freshly repeated:
every source recipe is unchanged, only those eleven raw record hashes and the
`data/items.json` input hash change. The old input guard first rejected the
changed data; no citation hashes were manually replaced.

An initial scratch citation observation was rejected because external file
synchronization introduced `Name clash` filenames for two class files. It is
retained as failed diagnostic evidence. The successful re-query used a fresh
unsynced temporary directory, checked its complete input inventory/hashes
before and after, and preserved all source recipes. The canonical result is
`capacity-correction/source-citations-23-verified.json`, not the earlier draft.

## Review and verification

An independent review reproduced a stale-proof import loophole: deleting a
changed file's hash could skip its check. The new `item_proof_inputs.py` guard
requires the exact complete four-file inventory, every current hash, the
current PDF hash and an actual Boolean success result for both new proof
imports. Mutation tests reject missing, extra and stale inputs. The reviewer
repeated the actual CLI bypass after the fix and confirmed rejection, then
successfully imported both current proofs. No remaining material findings
were reported in the reviewed scope.

The final complete source suite passes 112 tests with zero skips
(`candidate-23-source-tests-final.log`). The earlier 108-test run is retained;
the final run includes all four new proof-input mutation tests and the
corrected upper-bound evidence assertion.

Evidence under desktop `output/srd-fork/`:

- `candidate-23-capacity-boundary-proof.json`: exact field and all-output
  boundary, protected code and installed-data fingerprints.
- `candidate-23-ability-review/verification.json` and
  `candidate-23-capacity-review-final/verification.json`: fresh source facts,
  limits, conditions, unique references and guarded absences.
- `candidate-23-final-item-review/review.json`: consolidated field coverage.
- `capacity-correction/citation-refresh-boundary.json`: identical source
  recipes, exact eleven changed preimages, frozen input inventory and source
  model `e45936cf14c888ff21651b68588a9248dd3e4c31f2700d43445eada2de4e6bba`.
- `candidate-23-validation-final.json`: 40 JSON data files / 2,136 records,
  including retained capacity UID and positive-integer quantity checks.
- `candidate-23-pdf-and-preservation-proof.json`: binds the current manifest
  and identical HTML to the existing 186-page final desktop PDF certificate.
  This is explicit evidence reuse, not a new print or Android-native export.
- `candidate-23-rule-prose-locator.json`: all 653 non-character prose leaves
  locate exactly in the source; metadata and omissions are still separate
  gates, and the locator certifies zero complete records.

The fork remains unpublished and the default-download flows remain unchanged
until the remaining source, release, install and native-device gates pass.
