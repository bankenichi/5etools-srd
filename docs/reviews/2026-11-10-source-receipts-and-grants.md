# Source receipts and item grants — 2026-11-10

Candidate 24 adds only `Ranger` to the Druidic Focus `focus` class list, matching
the existing literal source sentence on SRD p97. No prose, table, name, price,
weight, grouping, splitting or renderer implementation changed. All 28 generated
desktop/Android HTML files are byte-identical to candidate 23; both retain
1,616 cards / 1,488 entries and every split/order/layout. The other 39 data files
are byte-identical. All 38 protected code files and 651 installed full-database
JSON inputs still match their frozen baselines.

## Source-projection provenance

`tools/projection_provenance.py` validates the complete authored receipt objects
after the family/equipment verifiers freshly prove their source models against
the physical PDF. The 150 `_srd521` objects now require the correct version,
official PDF hash, identity-selected heading/header, independently derived
whole-family page list, selected paragraph indices, exact authored scope note
and the correct source table projection. The 27 `_srd521Equipment` objects
require the exact source-unit order, official PDF hash and reviewed projection
model digest. Missing/unknown fields and Boolean/numeric aliases fail.

Table selection is independently derived from item identity. In particular,
Cloud/Fire/Frost/Stone/Hill/Storm Giant belt and potion variants cannot borrow
another otherwise-valid printed row. Group/helper full tables, concrete
Resistance tables and complete Spell Scroll tables retain their existing
projection rules. This strengthens verification, not data or grouping behavior.

These 177 objects are **authored provenance**, not 177 additional printed game
rules. They are explicitly classified that way in the consolidated report.
The aggregate verified-field total must not be interpreted as a percentage or
a complete source-fidelity certificate.

Independent review repeated the physical source verifiers, the receipt tests
and 1,415 missing/unknown-field mutations. It also found two importer gaps:
counts alone allowed substituted nonexistent identities, and inconsistent
`value`/`source_expected` facts could be published as verified. The importer
now requires complete actual/model identity sets, true Boolean literal/
structural flags, disjoint coverage, and type-aware equality among the actual
receipt, imported value and source expectation. Eight actual negative CLI
reproductions reject the corrupt proofs, while the current positive CLI passes.

## Language, proficiency, focus and scroll fields

`tools/verify_item_grants.py` freshly verifies 37 retained fields across 34
records: six language flags, three proficiency/training flags, four focus class
lists, fourteen focus categories and ten scroll levels. Source physical focus
grids and literal class clauses supply the answers. Scroll levels select the
printed row by identity; a physical source definition binds Cantrip to level
zero. Variant source scopes preserve the particular elemental plane.

Evidence retains wearing/holding, the Hat of Many Spells' extra Somatic
component, the deck's particular Throne outcome, and Elven Chain's training
with **that armor**, which the legacy schema indexes as `grantsProficiency`.
No grant of training with an entire armor category is asserted.

The pre-fix candidate-23 audit fails only for Druidic Focus's missing Ranger.
`corrections/zzzzzzz-item-focus.json` changes only `/focus`, with a complete
record preimage hash. The old source-citation guard rejected that change. All
2,136 citation queries were freshly repeated: every source recipe is identical,
only that record's hash and the item-file input hash change. The new source
model hash is `df463cc29657fa5f2c3152ddf8071e43df9688b36219b26a958bfc831324a795`.

Independent review confirmed the source findings, surgical data boundary,
identical HTML/counts/splits, installed-data preservation and protected hashes.
It found a per-record importer gap: aggregate counts allowed moving the Druidic
Focus field to a null field on Crystal. Each proof row must now certify exactly
the actual record's present grant fields. The reviewer repeated the corrupted
CLI after the fix (rejected), and the current proof still imports all 37 fields
with zero differences. No unresolved findings remain in that scoped review.

## Current evidence and limits

All 15 refreshed source component commands pass. The consolidated item report
verifies 2,690 enumerated fields across 730 records, including the 177 separately
classified provenance objects, with zero confirmed differences. Remaining
metadata/schema and all broader content/consumer gates remain explicit.

The final complete source suite passes 138 tests with zero skips
(`candidate-24-source-tests-final.log`). The focused grants suite also passes
all eight tests, including the actual corrupted-proof CLI regression. The
earlier 130-test provenance and 137-test candidate-24 snapshots are retained.

Evidence under desktop `output/srd-fork/`:

- `candidate-24-family-review/verification.json` and
  `candidate-24-equipment-review/verification.json`: current source/provenance.
- `candidate-23-provenance-import-recheck/verification.json`: actual CLI
  rejection of the substituted identities, inconsistent facts, missing input
  hashes and false literal flags in the unchanged-data provenance phase.
- `candidate-23-grants-review/verification.json`: the source-proven Ranger
  discrepancy before the guarded correction.
- `candidate-24-grants-review/verification.json`: all 34 current scopes.
- `candidate-24-final-item-review/review.json`: final current proof integration.
- `focus-correction/citation-refresh-boundary.json`: exact source re-query and
  immutable uncited observation.
- `candidate-24-focus-boundary-proof.json`: exact one-field data change and
  all 28 unchanged generated HTML files.
- `candidate-24-pdf-and-preservation-proof.json`: current manifest bound to the
  existing final PDF certificate for the identical HTML input. No fresh print
  or Android-native export is claimed.
- `candidate-24-install-probe/verification.json`: both helper copies install
  the exact 44-file private package, retain 1,616 / 1,488 cards/entries and
  reproduce all 28 HTML files byte-for-byte. Existing full data remains intact.
  This is an unpublished 881,650-byte fixture, not a verified public release.

No release, default-download, native-device or whole-SRD fidelity completion is
claimed. Those remain required before publication and goal completion.
