# Changelog

Notable changes to MedLite. Dates are ISO 8601.

## Unreleased

### Changed
- README rebuilt as a project landing page:
  - badges and light/dark screenshots;
  - overview, features and quick start;
  - architecture diagram, guardrail, evaluation, structure and limitations.

### Fixed
- Dark theme: the safety notice, the "no record" messages and the
  spelling-suggestion panel used a fixed dark-brown text colour, which was
  nearly unreadable on the dark background. They now use theme colours;
  the light theme is unchanged.

### Added
- `CITATION.cff` and this changelog.

## 2026-11-21: package refactor ([#1](https://github.com/kushagragupta2005/MedLite/pull/1))

### Fixed
- The app and the benchmark used different drug-name matchers. The app
  could not match names with punctuation (13% of DDInter aliases) or with
  more than four words, so it could silently skip a pair check.

### Changed
- The `baseline/med.py` monolith is now the `medlite/` package.
  `python3 baseline/med.py` keeps working.

### Added
- LLM output guardrail.
- A hardened local server.
- 49 tests and CI on Python 3.9 and 3.12.
- `pyproject.toml`.

## 2026-10-16: initial publication

- Offline lookup over DDInter with file-level provenance.
- Confirm-before-use spelling suggestions.
- Optional local-model summaries.
- Recognition benchmark tooling: gold-corpus validator, span scorer,
  SMM4H importer and submission packager.
