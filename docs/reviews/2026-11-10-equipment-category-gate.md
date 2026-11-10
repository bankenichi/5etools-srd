# Equipment-category source gate

The new read-only verifier extracts the complete printed Weapons and Armor
tables from the pinned official PDF. Painted cell geometry supplies all rows;
the four spanning category headings in each table supply the category facts.
Candidate values do not choose the source category or inventory.

Current result: 38 weapons, 12 wearable armor entries and one shield, with 139
positive fields verified. Exact itemType UIDs must resolve to helpers with the
correct category name. The consolidated item audit applies these facts to the
51 ordinary base items only. Magic inheritance and all other metadata remain
outside this component.

An independent reviewer reproduced the fresh extraction, all 139 facts, the
exact integration scope and stale-input rejection. It found one validation
gap: contradictory additional flags were ignored. Quarterstaff `armor=true`,
Plate Armor `weapon=true`, Shield `weapon=true`, and Plate Armor
`weaponCategory="martial"` all passed the initial gate. The actual dataset had
none of these defects.

The verifier now rejects incompatible flags or weapon categories, including
malformed numeric flags. An explicit Boolean false does not assert the opposite
category. Regression cases cover these findings, missing/duplicate/unprinted
rows, wrong enclosing categories and missing/duplicate/incorrect helper UIDs.
The same actual dataset still verifies exactly 139 positive fields; no content
or application code changed to obtain that result.

The reviewer also reproduced the separate three-record class-source boundary:
37 unchanged data files, the two complete printed Fighting Style alternatives,
and exactly seven removed foreign invocation nodes. These component checks are
not whole-SRD completeness or full-catalog PDF certification.
