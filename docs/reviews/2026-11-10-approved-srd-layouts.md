# Approved SRD-only layout metadata — 2026-11-10

The user explicitly approved “Apply the six data-only overrides” after reviewing
`candidate-18-layout-option-probe/review/existing-orientation-options.pdf`.
The later full-database invariant remains mandatory: preserve exact counts,
splits and existing behavior. No app renderer, parser, fitting, splitting or
grouping code was changed.

`source/layout-overrides.json` freezes the official PDF hash, upstream commit,
six exact record preimages/postimages, paragraph paths and paragraph hashes.
The normal builder first applies its guarded source citations, then wraps only
the designated literal paragraph using the app's already supported unnamed
`type: item`, `entry: <original text>`, `_force_portrait: true` shape.

| SRD record | Previous cards | Approved cards |
| --- | ---: | ---: |
| Chain Devil | 1 | 2 |
| Horned Devil | 1 | 2 |
| Kraken | 2 | 2 |
| Planetar | 1 | 2 |
| Mysterious Deck, Decks category only | 2 | 4 |
| Dragonborn | 1 | 2 |

Candidate 21 contains 1,616 cards / 1,488 entries on both frozen generators.
The Items-category Mysterious Deck is unchanged. The exact inverse restores all
2,136 candidate-20 source records across all 40 JSON files. Both platforms retain
the other **1,602 cards byte-for-byte, in order and with identical splits**.
The other ten category HTML files per platform are entirely byte-identical.

Source-only audits accept only the frozen exact inverse. Changed source prose,
extra wrapper keys, false/numeric flags, an additional landscape flag,
unreviewed markers and missing/duplicate approved records are rejected. Actual
file and record hashes remain bound in audit evidence; the normalized source
projection and model hash are identified separately. The citation source model
does not change for this presentation metadata.

Independent context-free review found no actionable material bugs. It reran all
seven override tests, validated all 40 files / 2,136 records, independently
compared the exact inverse and ordered card sequences on both platforms, and
confirmed no tracked desktop engine/parser change. The complete source suite
passes **76 tests, zero skips**. Five additional full-database preservation
gate tests pass separately.

Fresh candidate-21 item component proofs and consolidated review retain
**730 records / 2,294 enumerated verified metadata fields / zero confirmed
metadata differences**. Monster core/feature and all source-citation recipes
also replay successfully after strict inverse normalization. Many other
metadata, typography and omission checks remain open; these results are not
a complete source-fidelity certificate.

Desktop evidence, relative to `output/srd-fork/`:

- `candidate-21-layout-boundary-proof.json`
- `candidate-21-generators/verification.json`
- `candidate-21-source-tests.log`
- `candidate-21-item-review/review.json`
- `candidate-21-monster-review/comparison.json`
- `candidate-21-citation-review.json`
- `full-database-preservation-baseline/verification.json`

The installed full database stays untouched: 651 JSON inputs / 29 unrestricted
official/playtest requests generate **12,270 cards / 10,183 entries / 1,374
sheets** per platform. Fresh reruns are exactly equal to each platform's own
complete HTML/card/shell baseline. The initial uninitialized Android host test
was superseded after reproducing the app's existing deity-cache startup call.
Existing cross-platform body/style/source-label differences remain explicit;
they have not been changed to force parity. See the desktop review
`docs/reviews/2026-11-10-full-database-rendering-preservation.md`.

The initial candidate-21 export passed MuPDF but failed PDFium on 43 bestiary
pages, with at most 853 differing pixels and zero unexpected contrast tiles.
The failed PDF and diagnosis are preserved in `candidate-21-full-export/`.
The defects were one-pixel darker seams between exactly adjacent translucent
table-cell fills. A guarded PDF-only raw-byte union now removes those internal
edges without altering HTML, text, curves, coordinates or rendering code.
It runs before final drawing hashes are frozen; downstream guards and all
visual/glyph tolerances remain unchanged. Independent review found no issues.

The fresh production export in `candidate-21-final-export/` is **186 Letter
pages / 1,616 cards / 19,604,985 bytes**, SHA-256
`c887c89ccc22874cde804e01b387efc09321b67c42d37f7f9bf5943d5c4a5207`.
All 186 native drawing streams before that PDF-only step are identical to the
initial export, as are every browser glyph layout, text signature and card
count. All 1,001,414 characters match; zero glyphs are unmatched. Maximum
advance/cross error remains 0.10385 / 1.8035 CSS px. Both independent readers
pass every page at 300 DPI: maximum quiet-background differences are two
pixels in MuPDF and zero in PDFium. The PDF-only change passes 98 scoped app
tests; the workspace suite including the separate installer tests passes 108.

Every assembled-PDF page was inspected in six overview images. Detailed actual
PDF crops of all 14 approved card faces were inspected too: formerly clipped
content and table rows are present, without opaque mask boxes. The export is
one complete native-vector searchable PDF, with internal per-sheet processing.
Font antialiasing differences mean this is not literal pixel identity.
Final evidence: `candidate-21-final-export/all.pdf`, `verification.json`,
`glyph-verification.json`, `graphics-mupdf.json`, `graphics-pdfium.json`,
`browser-boundary.json`, and `review/`. Browser screenshot 45 has edge raster
variation within the unchanged checks; its glyph layout and native stream
remain exact. See desktop `docs/reviews/2026-11-10-pdf-cell-seams.md`.

This is desktop candidate-PDF verification. The remaining complete source,
consumer-output, data-only release, actual default-download, native-device,
fresh-install and scoped publication gates still apply.
