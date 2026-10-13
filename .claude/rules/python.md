---
paths:
  - "**/*.py"
---

# Robust Python Conventions (Patrick Viafore)

## Project specifics

- ruff is strict: on top of the usual sets it enables `TRY`, `EM`, `FBT`, `T20`, `PL`,
  `SLF`, `TC`, `TID` (no relative imports) and `INP`. Fix the code rather than adding
  `noqa`; a justified ignore names its code and reason (`PGH`). Typer commands are
  exempt from the argument-count rules (`PLR0913`, `PLR0917`).
- mypy runs in `strict` mode (plus `warn_unreachable` and extra error codes) on
  `src` and `tests`. Tests are not annotated (ruff `ANN` is off for them, and so are
  the untyped-def checks for the `tests` package), but their bodies are type-checked.
- numpy-style docstrings on every public module, class and function (ruff `D`), with
  doctest `Examples` where they help: pytest runs doctests (`--doctest-modules`).
- One import per line (`isort force-single-line`), line length 88. Error messages go
  in a `msg` variable before the `raise` (`EM`).
- Models mirroring an API response (STAC, Process API errors, tokens) are Pydantic
  models with `extra="ignore"`; the private ones (`_Feature`, `_Page`) stay inside
  their module and are mapped to a public frozen model (`Scene`).
- Geographic values get validated types: `BBox` (WGS84, lon/lat, checked in
  `__post_init__`), `DayRange` (inclusive UTC days). Never pass bare
  `[w, s, e, n]` lists or naive datetimes around; convert at the API edge.
- Closed sets are `StrEnum` (`Site`, `Evalscript`, `DataCollection`, `Mosaicking`),
  with exhaustive `match` + `assert_never` where each member maps to data.
- Evalscripts are `.js` files in `src/copernicus/evalscripts/`, loaded through the
  `Evalscript` enum, never inlined in Python strings.
- Secrets: credentials come from `CdseSettings` (pydantic-settings, `SecretStr`, env
  or `.env`). Never log, print or put a secret in an exception message.
- Tests live in `tests/` (a package, with `conftest.py` helpers), grouped in pytest
  classes (`class TestX:`), `tmp_path` for files, `httpx.MockTransport` for HTTP (no
  network in tests, ever: the Stop hook runs them), `typer.testing.CliRunner` for
  the CLI.

Core principle: **communicate intent through types** so future maintainers can trust the code without reading every line. Robustness = code that is resilient and error-free in spite of constant change.

## Types as Communication (Part I, ch 2-7)

- **Type annotations on all public APIs**: every function signature, return type, and class attribute must be annotated. `mypy --strict` is the goal.
- **Constrain types tightly**: use `Optional` only when `None` is meaningful, `Literal` for a handful of fixed values, `Final` for constants that must not be reassigned.
- **`Annotated` / `NewType` for domain concepts**: distinguish domain strings (`ProductId`, `TileId`) from generic `str` so accidental swaps are caught by the type checker.
- **Collection type precision**: accept the narrowest type that works — `Sequence` over `list`, `Mapping` over `dict`, `Iterable`/`AsyncIterable` for streaming. Return concrete types. Distinguish homogeneous collections from heterogeneous ones (`TypedDict`).

## User-Defined Types (Part II, ch 8-13)

- **`StrEnum` for closed sets**: when a value must be one of a known set, model it as a `StrEnum` — not a bare `str`. Prevents invalid values at construction and gives autocomplete. Examples: `Site`, `Evalscript`, `ImageFormat`.
- **Dataclasses / Pydantic models over dicts**: structured data gets a named type with typed fields — never a plain dict. Dicts are for dynamic key-value lookups. Use Pydantic `BaseModel` with `Field(description=...)` and `ConfigDict(extra="ignore")` for API models.
- **Classes for invariants**: reserve classes (with `__init__` logic) for when you need to enforce an invariant. If there's no invariant to protect, a dataclass or Pydantic model is simpler.
- **Protocols over inheritance**: define interfaces with `Protocol` (structural subtyping / duck typing) rather than ABC inheritance, unless you need shared implementation. Keeps coupling low.
- **Composition over subclassing**: prefer composing small objects rather than building deep inheritance trees. Use subtyping only when true substitutability (Liskov) holds.

## Extensibility (Part III, ch 14-19)

- **Explicit over implicit**: exhaustive `match`/`case` over open-ended `if`/`else` chains. Every branch must be visible — no implicit fallthrough. Follow the Law of Least Surprise: a function named `get_X` must not mutate state.
- **Constrain, don't validate late**: push constraints into the type system (enums, `Annotated`, pydantic validators) rather than sprinkling runtime checks. Invalid states should be unrepresentable.
- **Design for extension points**: when an area of code changes often, isolate the varying part behind a protocol or callback so new behaviour can be added without modifying existing code.

## Safety Net (Part IV, ch 20-24)

- **Testing strategy**: unit tests as baseline, property-based tests (Hypothesis) for edge-case discovery, mutation testing (mutmut) to verify test suite quality. Neither Hypothesis nor mutmut is installed: add them to the dev group only when a tool actually benefits.
- **Static analysis as first line of defence**: lean on ruff, mypy, and type annotations to catch bugs before tests run.
