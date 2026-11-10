# Reproduce the source audits

The source-audit tools need Python and the dependencies in
`tools/requirements-audit.txt`. The data builder itself uses only the standard
library and Git. Keep the pinned upstream commit available in the local Git
object database; it is recorded in `tools/build_srd.py`.

Download the official SRD 5.2.1 PDF from
<https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf>.
Every PDF audit rejects a file whose SHA-256 is not
`8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87`.
Keep this source file outside the dataset directory.

From this repository, using PowerShell and a Python environment with the audit
dependencies installed:

```powershell
python -m pip install -r tools/requirements-audit.txt
python tools/build_srd.py --out C:/path/to/candidate
python tools/validate_srd.py C:/path/to/candidate
$env:SRD521_PDF = 'C:/path/to/SRD_CC_v5.2.1.pdf'
python -m unittest discover -s tests -v
python tools/verify_rule_tables.py --pdf $env:SRD521_PDF --data C:/path/to/candidate --out C:/path/to/rule-table-review.json
python tools/class_spell_lists.py --pdf $env:SRD521_PDF --data C:/path/to/candidate --out C:/path/to/class-spell-list-review.json
python tools/verify_magic_item_headers.py --pdf $env:SRD521_PDF --data C:/path/to/candidate --out C:/path/to/item-header-review
python tools/verify_item_resources.py --pdf $env:SRD521_PDF --data C:/path/to/candidate --out C:/path/to/item-resource-review
python tools/verify_equipment_categories.py --pdf $env:SRD521_PDF --data C:/path/to/candidate --out C:/path/to/equipment-category-review.json
python tools/verify_item_base_bindings.py --pdf $env:SRD521_PDF --data C:/path/to/candidate --out C:/path/to/base-binding-review
python tools/verify_source_citations.py --pdf $env:SRD521_PDF --data C:/path/to/candidate --out C:/path/to/citation-review.json
```

Without `SRD521_PDF`, the independent PDF tests are explicitly skipped. A run
with skipped source tests cannot certify the data. The table checks reopen the
official PDF and recover cells from its painted rectangles, source typography
and continuation headers. Saved JSON source models alone are not proof.

The item-header/resource verifiers also reopen the source PDF and re-prove all
family models before using any variable rarity or selected subtype paragraphs.
The family checks require complete source glyph/header inventories as well as
exact row associations; a matching subset of source rows cannot pass.

The ordinary equipment-category verifier recovers both complete six-column
source grids and their spanning category rows. It checks 38 weapon rows plus
12 wearable-armor rows and one shield row: 139 positive facts about type UIDs,
weapon categories and category flags. Typed helpers must have the right meaning,
not merely a matching abbreviation. Missing/duplicate/unprinted base rows,
contradictory category flags, non-Boolean flags and wrong helper meanings fail.
This does not certify magic-item inheritance or other metadata. The resulting
input-bound report can be supplied as `--category-proof` to the consolidated
`tools/item_audit/review_details.py` audit alongside its other component proofs.

The base-binding verifier supplies another input-bound report via
`--binding-proof`. Printed fixed subtypes choose their ordinary base item;
printed Staffs/focus clauses choose normal Quarterstaff use. This verifies 167
fields on 44 current records, including all 25 remaining weapon-category fields.
It checks helper UID meanings, unique projection identities and complete source
staff/focus coverage. Missing members cannot be hidden by duplicate substitutes.
Magic bonuses, special forms, five Horn bindings and generic-variant predicates
remain outside this component; the general staff clause is explicitly nonmagical.

The builder applies `source/citations.json` only when its full uncited input
record inventory/hashes match. Source IDs, structural references and citation
pages change together. `verify_source_citations.py` keeps these guards enabled,
observes the pre-citation input, replays every reviewed PDF query, and compares
the actual dataset bytes with the guarded rebuild. An empty compatibility helper
is explicitly distinguished from a printed entity. The source index covers all
336 consolidated statblocks.

Future data corrections require a new observed uncited projection and a fresh
PDF citation audit when those frozen inputs change. Do not bypass the normal
builder's citation checks or publish a provisional/uncited projection.

The three typed-class-reference corrections also have a data/HTML boundary
check, run against frozen before/after datasets and independently generated
desktop/Android HTML directories:

```powershell
python tools/check_typed_reference_boundary.py --before C:/path/to/candidate-17 --after C:/path/to/candidate-18 --before-html C:/path/to/candidate-17-generators --after-html C:/path/to/candidate-18-generation --out C:/path/to/reference-boundary.json
```

It verifies the exact three data edits, unchanged file inventory, complete
Paladin/Ranger body text except the two printed insertions, unchanged card
counts/titles and every other card, and unchanged HTML outside card faces. The
two source paragraphs can reflow existing class cards without changing the
splitting code. The source tests independently recover both full paragraphs and
the entire 28-entry invocation heading inventory from the official PDF.

These are component audits. They do not establish whole-SRD completeness,
unreviewed mechanics/metadata, card layout or final-PDF fidelity. Current open
gates and evidence checkpoints are listed in `srd521-audit-progress.md`.
