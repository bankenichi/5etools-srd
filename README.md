# SRD 5.2.1 data

SRD 5.2.1 (2024 rules), represented as 5etools-compatible structured data for
TTRPG Card Generator. The current data directory contains only this SRD
projection: 40 JSON files and 2,136 records, including 339 spells and 336
creature statblocks. Empty category files preserve importer compatibility.

[Download the data-only ZIP](https://github.com/bankenichi/5etools-srd/releases/download/srd-5.2.1-r1/srd-5.2.1.zip).
The archive contains data, its checksum manifest, this README, attribution and
the data license. It contains no card-rendering code or upstream website.

The projection retains source rules and tables, source-backed corrections,
typed references and SRD naming. Authoring helpers and compatibility indexes
are identified separately from printed game rules. Six explicitly approved
SRD-only orientation flags use existing generator settings. No renderer or
splitting engine is included or modified by this dataset.

## Attribution and license

See [ATTRIBUTION.md](ATTRIBUTION.md) for the required SRD attribution and
[DATA-LICENSE.md](DATA-LICENSE.md) for CC BY 4.0. Software licensing is separate
in [LICENSE.md](LICENSE.md).

## Rebuild

Python and Git are sufficient for the deterministic data build:

```powershell
python tools/build_srd.py --out C:/path/to/staging
python tools/validate_srd.py C:/path/to/staging
```

The builder reads upstream commit
`32ef600fab87a585a61dd1a22e9b02dfc58c728a` from the Git object database.
Clone with history available; a source ZIP alone does not contain those Git
objects. The current tree is pruned; the fork's upstream ancestry remains in
Git history. This is why app downloads use the data-only release asset.

Source evidence and build policies are in `source/` and `corrections/`.
Reproduction notes are in [docs/source-verification.md](docs/source-verification.md).
The manifest records source provenance and every data-file checksum; it is
not a claim of pixel identity between different PDF viewers or platforms.
