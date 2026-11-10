# Lighting, poison and movement source checks — 2026-11-10

Candidate 23's data is unchanged. The new read-only environment audit verifies
75 additional retained query fields across 61 item/variant records directly
against the pinned official PDF:

| Field | Verified fields | Independent source |
| --- | ---: | --- |
| `light` | 20 | Literal clauses and crab lever-8 Up cell |
| `poison` | 15 | Fourteen printed poison headers plus Basic Poison rule |
| `poisonTypes` | 14 | Contact/Ingested/Inhaled/Injury italic headers |
| `modifySpeed` | 11 | Identity-scoped magic-item rules |
| `speed` | 8 | Named animal statblocks, bound to printed mount rows |
| `vehSpeed` | 7 | Complete physical vehicle grid, mph and exact half units |

`tools/verify_item_environment.py` never uses a candidate value to select the
answer. It re-proves all source family models and their physical row mappings,
then binds particular item identities to source rules. Air-plane ring metadata
cannot borrow Water-plane movement. Mount equipment rows do not print speed;
their values are instead proven from each named animal's actual Speed statline
in its own source statblock, retaining that derivation explicitly.

Lighting's `dim` value is the total outer extent, not just the additional dim
annulus. Cone shape and the two lowered/raised hood modes remain distinct.
The crab's source lever includes both its activation and light-off positions.
Source evidence retains fire opal/diamond distinctions, the produced energy
arrow rather than a constant bow aura, Frost Brand's freezing-temperature
condition, activated light durations and Sun Blade's adjustable sunlight limits.
Movement evidence retains wearing/holding, activation/charges, time limits,
hovering, descent, slippery-surface restrictions and the higher-existing-Speed
exception. Query fields describe available effects; literal prose retains the
complete rules. Optional source effects without an existing query index are
not invented or certified as unconditional grants.

The proof importer requires exactly the complete four-file input hash
inventory, current data/PDF hashes, the current family-model hash, 61 unique
record identities and the complete per-field counts above. Consolidated
evidence now verifies 2,476 enumerated fields across the 730 assigned item
records, with zero confirmed differences. No environment field remains in its
unproved inventory. Other schema/provenance, metadata, typography, omissions
and consumer gates remain explicit. This is not a whole-SRD certificate.

Independent review repeated the fresh extraction/audit, reconciled a separate
raw-file inventory, mutated all 75 fields (all rejected without changing the
source-derived answer), and checked missing/extra/stale inputs, failed receipts
and stale PDF rejection. Actual `review_details.py --environment-proof`
imports all 75 fields successfully. No findings were reported. Eight focused
tests and the final complete 120-test source suite pass, with zero skips.

Evidence under desktop `output/srd-fork/`:

- `candidate-23-environment-review/verification.json`: all source scopes,
  printed cells, statlines, poison headers and conditional effects.
- `candidate-23-environment-item-review/review.json` and
  `remaining-field-inventory.json`: current consolidated coverage and gaps.
- `candidate-23-environment-source-tests.log`: 120 passing source tests.
- `candidate-23-install-probe/verification.json`: fresh candidate installs via
  the desktop and Android helper copies into separate isolated roots. Every
  package byte and all 28 generated HTML files match the original candidate;
  both retain 1,616 cards / 1,488 entries. The 880,333-byte private archive is a
  test fixture, not a public source-approved release.
- `candidate-23-install-probe/runtime-tests-receipt.json`: ten runtime-only
  integrity, rollback, archive and redirect tests pass per helper copy.

No app engine, parser, fitting, splitting, grouping, download default or
installed catalog was modified. This install test verifies the actual helper
copies and generators on the host, without public network/UI/native-device
claims. The existing final PDF certificate remains applicable to the identical
generated HTML; no new PDF was printed in this pass.
