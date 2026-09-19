# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-09-19

### Added

- Cell model with validation and a built-in library of six cells (Samsung 30Q, 35E and
  50E, LG HG2, Molicel P42A, A123 ANR26650M1-B). Every value is transcribed from the
  manufacturer datasheet named in the cell's `source` field.
- Custom cell libraries from JSON files.
- Pack analysis: voltage window, capacity, energy, internal resistance, voltage sag,
  heat per cell, output power and runtime.
- Main fuse selection and AWG wire sizing (ampacity and voltage drop).
- Pack sizing from requirements with ranked candidates and rejection reasons.
- `packdesign` command-line interface with text, Markdown and JSON output.
- `packdesign plot load` and `packdesign plot tradeoff` charts (PNG, SVG or PDF; light
  and dark themes; colour-vision-deficiency-validated palette), with matplotlib as an
  optional `plot` extra.
- Documentation of all equations with a worked example in `docs/theory.md`.
- Test suite with 100 % coverage, including tests that pin the cell library to the
  datasheet values and keep the README examples correct.
- Continuous integration on Linux and Windows, Python 3.10 to 3.14.
