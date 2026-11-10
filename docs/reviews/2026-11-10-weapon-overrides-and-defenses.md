# Weapon overrides and item defenses — 2026-11-10

Candidate 22 changes exactly two stale `resist` metadata flags in the SRD-only
projection. Source text, names, numbers, tables, page citations, the six approved
portrait wrappers and all app code remain unchanged.

| Record | Removed flag | Printed SRD 5.2.1 rule |
| --- | --- | --- |
| Ring of Elemental Command (Fire) | Fire Resistance | Fire Immunity while wearing the ring, from the Fire-plane focus; pp237–238 |
| Ring of Warmth | Cold Resistance | Reduce Cold damage taken by 2d8 while wearing the ring; p239 |

`corrections/zzzzz-item-defenses.json` freezes complete preimages and removes
only `/resist` on those two records. It retains all printed rules and the
fire ring's actual Immunity. The source audit also handles Periapt of Proof
against Poison's combined condition/damage Immunity clause; that is not a
data defect.

The weapon override audit independently reads all 258 printed magic-item
headers and physical glyph lines. It reconstructs source line wraps using
unbroken spellings elsewhere in the official PDF, without candidate numbers or
private paragraph indexes selecting answers. Its six relevant source headings
include Energy Bow, whose `Pierc-/ing` wrap makes a simple substring scan miss
its produced-arrow rule.

- Three property arrays, two ranges and Sun Blade's Radiant replacement are
  verified from source: Dwarven Thrower 20/60, Quarterstaff of the Acrobat
  30/120 in Quarterstaff form, and Sun Blade's active blade. Inherited Versatile
  comes from the independent physical weapon table. Property helper UIDs must
  resolve to the correct names and meanings.
- Hammer of Thunderbolts' charge expenditure, Javelin of Lightning's optional
  per-hit replacement and Energy Bow's produced-arrow condition are recorded
  separately. No universal metadata claim is certified for those effects.
- The defense audit reopens the thirteen-type Damage Types table and re-proves
  the family models. Identity chooses a source row or plane, never the proposed
  defense value. It verifies **58 fields across 56 existing projections**:
  53 Resistance, two Immunity and three Vulnerability arrays. Ring of Warmth is
  reviewed as a non-Resistance damage reduction, with no defense array.
- Full source scopes retain Helm of Brilliance's ruby/wearing condition,
  potion durations, holding conditions and Armor of Vulnerability's persistent
  curse. Missing, duplicate, substituted and out-of-inventory defenses fail.

Source citation refresh used an observational uncited snapshot, preserving the
old guard failure before updating anything. The existing index builder supplied
the five absent indexes, all exactly matching the previous model. All 2,136
source queries were repeated: every recipe/page is unchanged; only the two
corrected record hashes and the item file's input hash differ. The normal
guarded builder and 40-file / 2,136-record validator pass.

**Rendering preservation is exact:** 39/40 data files are byte-identical, and
removing those two flags is the entire semantic diff in the remaining file.
All **28 generated HTML files**, across desktop and Android, are byte-identical
to candidate 21. Counts remain **1,616 cards / 1,488 entries**, with all card
splits, order, markup and shell unchanged. The already verified final desktop
PDF is reusable because its exact generated HTML input is unchanged; no new
rendering input was introduced. The installed full database remains separate.

The complete source suite passes **94 tests, zero skips**. Eleven refreshed
component jobs pass. The consolidated item audit now verifies **2,358 enumerated
metadata fields across 730 records, zero confirmed metadata differences**.
Many remaining fields and broader source/consumer/omission gates are still
unproved; this is not a whole-SRD fidelity certificate.

Independent context-free reviews found no material issues. The weapon review
reran six tests and rejected stale digests for all four bound input files. The
defense review reran seven tests, independently checked the two-field and
28-HTML-file boundaries, and rejected 174 additional invalid field mutations.

Desktop evidence under `output/srd-fork/`:

- `candidate-22-defense-boundary-proof.json`
- `candidate-22-validation.json`, `candidate-22-generators/verification.json`
- `candidate-22-source-tests.log`, `candidate-22-component-jobs.json`
- `candidate-22-weapon-override-review/verification.json`
- `candidate-22-defense-review/verification.json`
- `candidate-22-item-review/review.json`
- `defense-correction/citation-refresh-boundary.json`
- `candidate-22-unchanged-monster-proof.json`

The last item explicitly reuses the unchanged bestiary's candidate-21 audit
against identical input bytes, rather than presenting it as a new monster run.
