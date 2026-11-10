# SRD 5.2.1 pruning plan

- [x] Fork and verify latest upstream main; leave installed data intact.
- [ ] Inventory all selected root records, aliases, helper references and possible content differences.
- [ ] Implement a pinned-input Python builder with explicit source selection, safe helper closure, aliases and documented official-text corrections.
- [ ] Produce only data/schema-compatible indexes, licenses, documentation, builder, manifest and tests on the fork main branch.
- [ ] Verify every retained record has a selection reason; validate all typed structural references and restrict ancillary metadata.
- [ ] Compare content against official SRD and require known non-SRD material to be absent.
- [ ] Generate every supported category with both existing renderers, without installing/switching the dataset or editing renderer files.
- [ ] Run deterministic rebuild, tests, independent review, and JSON/ZIP installation validation.
- [ ] Commit/push the pruned branch and verify the remote SHA; link the completed fork and disclose the upstream ancestry boundary.
