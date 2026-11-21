
# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.999.1] - 2026-11-21

### Changed
- Fork-only immutable release rehearsal. Registry publication is disabled.

### Added
- `expected.error_detail`: an optional negative-case file (Core §13.1, §13.2c; Extension §13.3.4)
  holding one substring per line. When present, a failing implementation must match at least one
  line, so "rejected with the right code for the wrong reason" no longer passes. Applied to the
  38 PNG rejects that all share `PXL006`; `python_ref_verify` and the Java PNG gate both enforce it.

### Fixed
- Core §8.5 now states that a value check depending on another chunk must first establish that the
  chunk has appeared. Concretely: a palette image whose `tRNS` precedes `PLTE` is an ordering
  rejection, not a "tRNS longer than PLTE entries" rejection. The Java decoder compared against a
  fallback of zero entries and reported the length rule, while the importer reported the ordering
  rule - same code, different first-failing rule. Java now checks ordering first, and a new
  `neg-png-trns-length-over-plte` case keeps the length rule covered on its own.
- The normative text claimed `PXL001` for every non-zero `version` while the wire format has
  been version 1 throughout. `spec/PXL.md` now states one rule in Core §3.2, §11 and §12:
  an in-domain version the compiler does not support is `PXL007`, and only a missing,
  non-integer, negative, out-of-domain or unrepresentable value is `PXL001`.
- `version` is no longer described as a reserved field next to `variant`; `bindings` is
  described as a compile-session input (Extension §6.3) rather than a document field.
- The core scope statement no longer claims that PXL never enters a build pipeline.
- Added conformance coverage for the version dispatch: `neg-version-zero` and
  `neg-version-unsupported` (`PXL007`), `neg-version-not-integer` (`PXL001`) in the base
  suite, and `neg-version-in-domain-unsupported` in the components suite. Generator and
  reference oracles now reject in-domain versions with `PXL007` instead of `PXL001`.
- `check_spec_sync.py` takes section numbers in full and ignores `PRD Extension §x`
  provenance, and the English section map now lists exactly the identifiers the Chinese
  text carries instead of seven identifiers that existed nowhere in the specification.
- `ci.yml` runs `check_spec_sync.py` and `check_release_metadata.py`; both were required by
  `AGENTS.md` but never executed by CI. README and CONTRIBUTING list the same gates as
  `AGENTS.md`.
- 45 stale `AGENTS.md §x.y` citations across the spec, tools, tests, Java sources and the
  corpus pointed at a numbered section layout that no longer exists; they now cite the
  seven contracts, and historical references are marked as such.

## [0.1.0] - 2026-11-12

### Added
- First public PXL version 1 specification and conformance corpus.
- Deterministic Java and Python compilers, PNG importer, and Gradle integration.
- PyPI, Maven Central, and GitHub Release packaging metadata.

[Unreleased]: https://github.com/gt6-modern/texel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gt6-modern/texel/releases/tag/v0.1.0
