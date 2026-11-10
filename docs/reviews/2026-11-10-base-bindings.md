# Fixed base-item and staff source bindings

`tools/verify_item_base_bindings.py` reopens the pinned official PDF. Its physical
magic-item headers select fixed Armor/Weapon subtypes; the complete ordinary
equipment grids supply category facts. The printed Staffs rule on p205 and
focus rows on p96/p97 explicitly select Quarterstaff statistics from p91.

The general staff clause says **nonmagical Quarterstaff**, unless its own
description says otherwise. This component verifies normal base-weapon dice,
category, Versatile property and Topple mastery. It does not grant a magical
weapon flag, additional attack/damage/AC bonuses, transformed-form statistics or
other conditional effects. Literal descriptions preserve those separate rules.

Fresh results cover 44 records and 167 positive fields:

- 30 fixed concrete item/group bindings, including the Dragon Scale Mail family;
- 12 printed Staff entries;
- two ordinary focus staffs explicitly described as also a Quarterstaff.

These are 30 `baseItem`, 42 `type`, 25 `weaponCategory`, and 14 each of `dmg1`,
`dmg2`, `dmgType`, `property`, and `mastery`. This completes the remaining weapon
category checks, but leaves the five Horn base-item links, generic-variant
predicates and many other fields unproved. Helper UIDs must resolve to uniquely
matching names/meanings. Unqualified `V` on the focus staffs uses the existing
5etools default-source compatibility alias (`Renderer.item._addProperty`, pinned
upstream `js/render.js`); an ambiguous second namespace is rejected by the audit.

Independent review reproduced the actual source facts, the narrow integration
scope and input hash binding. It found that a missing projection could be hidden
by a duplicate: Fire replaced by a second Frost staff, a Dragon Scale Mail color
replaced by another copy, or Staff replaced by a second Wooden Staff. The audit
now requires unique projection identities, exact staff-heading/focus-row
coverage and matching indexed record identities. Regression cases reproduce
all three substitutions. Current data needed no changes.

The final component report is desktop
`output/srd-fork/candidate-18-base-binding-review-final/verification.json`.
The consolidated 730-record item report has 2,228 enumerated verified fields,
zero confirmed metadata differences and many remaining unproved fields, at
`candidate-18-binding-final-item-review/review.json`. These component passes do
not certify whole-SRD completeness or rendered/PDF fidelity.
