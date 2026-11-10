# Reviewed source corrections (work in progress)

These data-only corrections are checked against the official English SRD 5.2.1
PDF, SHA-256
`8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87`.
Every patch records the expected projected-record hash, source pages, evidence,
and edited fields. A changed input fails instead of applying silently.

The selected upstream Git revision is only an input, not an authoritative SRD
transcription. Its `srd52` flags do not certify text, mechanics, completeness, or
tables. Retained commercial-source identifiers are compatibility keys, not SRD
page locators. The per-correction official pages are separate provenance.

The dataset is **not ready for publication or the default download**. Remaining
gates include items and helpers, non-character rules, literal character/monster
typography, additional structured metadata, source omissions, and existing
consumer text-formatting gaps. No app renderer, fitting or splitting code is
changed by these corrections. Generator parity alone is not source fidelity.

The spell verifier independently reads the official PDF. It compares all 339
bodies, printed header facts and class lists and retains its extraction spans,
table panel assembly, and line-break hyphen decisions. The current nine metadata
mechanics corrections are applied, but one literal duration punctuation mismatch
remains explicit. Four embedded summoned-creature blocks are covered by the
separate monster audit. Material text remains complete; ambiguous optional
aggregate ingredient cost/consumption scalars are omitted rather than misstate
the source.

The character corrections replace invented repeated-level prose with literal
source paragraphs or an empty structural table-row body, preserving every
existing feature reference and level. Source spell tables, remaining metadata,
and all typography are separate unfinished checks.

Two exceptional creature passive-Initiative values are stored as explicit
`initiativePassive` source facts. This additive data field avoids encoding an
inferred `advantageMode` and introducing an unprinted Advantage rule. Existing
consumers may ignore that extra field; consumer formatting remains a separate
gate. All 30 legendary headers use the literal source through the already
supported `legendaryHeader` field.

Display tags are materialized as literal text in the new dataset because the
apps' existing cleaners omit modern save/attack labels and some dice display
values. Structural `filter` tags remain: class-table consumers inspect their
parameters to preserve table splitting. No app parser or renderer is changed.
