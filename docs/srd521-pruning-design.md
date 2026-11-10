# SRD 5.2.1 data-only fork

User-approved scope: fork the current GitHub upstream and prune to SRD 5.2.1 only (2024 rules). Upstream is 5etools-mirror-3/5etools-src, commit32ef600fab87a585a61dd1a22e9b02dfc58c728a, v2.41.0. Fork: bankenichi/5etools-srd.

Keep the 5etools-shaped data paths consumed by the existing desktop and Android card generators. The fork is a database distribution; website code, generated search payloads, images, audio, adventures, full commercial books, homebrew and playtest content are excluded from the active branch and ZIP. Both installed databases and both renderers remain unchanged.

Selection begins with explicit srd52 markers (including magicvariant.inherits.srd52), not Basic Rules or the older srd marker. String markers are SRD names and must replace the original titles and references. Retain only required mechanical helper records; never pull an unflagged full entity into the dataset just to satisfy a reference. Rebuild indexes and empty category files for loader compatibility. Strip outside-source, artwork, lore, version and unrelated feature-progression metadata.

Flags are not proof that every paragraph is in the SRD. Verify selected prose against the official 364-page SRD5.2.1 PDF, including the known Dragon Orb lore difference, and record corrections explicitly. Fail validation on unresolved structural references, known excluded material or stale indexes. Preserve the SRD attribution and upstream MIT code license separately.

Build from a pinned upstream Git revision so pruning can be reproduced without retaining the removed content in a second working-tree directory. Tests must prove SRD-only selection, aliases, no unsupported dependency promotion, deterministic output, intact tables and references, and generator compatibility. Generate a manifest with input revision/PDF hash, counts, policy decisions and output hashes.

A GitHub fork retains upstream ancestry. Only the current branch tree and its generated release ZIP are the SRD-only distribution; pruning does not erase upstream Git history.

## Exact-fidelity goal, added November 10

The user explicitly requires SRD content to be 100% identical to SRD5.2.1, and the verified SRD dataset to become the default download in both desktop and Android. Coverage, prose, names, mechanics, numeric values and tables must be traced against the official document across the complete published dataset. Upstream srd52 flags, approximate text matching, sample checks, or successful generation are insufficient proof of exact content fidelity. No invented explanatory prose, merely compatible paraphrase, or unverified repair of the official text may pass this gate. Only representation differences needed by the established JSON schema may be normalized, with a lossless mapping and validation evidence.

Defaults may change only after the fidelity gate passes. Preserve custom URL/ZIP choices, installed databases and the existing rendering, fitting and splitting engines. Test the fresh default-download flow on both platforms and verify the published artifact, rather than relying on a local staging build.

The user additionally requires one discreet SRD attribution notice in each app, using the statement required by the official SRD's Legal Information page. Expose it through an About & licenses destination; do not put it on cards or alter card layouts. This notice is a goal acceptance requirement for both desktop and Android.
