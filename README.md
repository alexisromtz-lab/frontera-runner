# frontera-runner

One subject in. One sealed receipt out. Four instruments that live in four other repositories,
called as subprocesses, never imported.

The point is not to run four linters. The point is to publish **one** verdict a pull request can
read, in which an instrument that had nothing to measure says so by name instead of returning a
green zero.

```
frontera-runner <sujeto>            # Markdown for a PR check
frontera-runner <sujeto> --json     # the canonical receipt
```

## Why this exists

Three of the four instruments return `2` when they find no universe: `fiber-ast-lint` with no
Python analysed, `test-ordinal-ratchet` with no test file parsed, `ts-py-anchor-guard` with
nothing evaluable. A composite runner that folds `2` into "0 findings" turns *we did not look* into
*we looked and it is clean* — the exact defect the four instruments were built to refuse, reintroduced
at the layer that aggregates them.

So the runner maps every exit code each instrument can emit, and the two states that mean "no
measurement" carry a machine-readable reason:

| state | meaning | carries `hallazgos`? |
|---|---|---|
| `APLICABLE` | the instrument ran over a universe it saw | yes, an integer |
| `NO_APLICABLE` | there was nothing to measure, and the reason is on the row | no, `null` |
| `NO_MEDIDO` | there was something to measure and it was not measured | no, `null` |
| `NO_EJECUTADO` | the instrument's repository is not where `--raiz` says | no, `null` |

## The four instruments

Called as `python -m <module> <args>` with the subject as the working directory, and with
`PYTHONPATH` pointing at the instrument's own repository — a `src/` layout is not optional.

| instrument | invocation | exit codes |
|---|---|---|
| `git-complement-audit` | `-m git_complement_audit . --json` | `0` nothing outside `HEAD` · `1` orphan code or secret risk · `2` invalid repository |
| `fiber-ast-lint` | `-m fiber_ast_lint.cli . --json` | `0` no candidates · `1` candidates · `2` empty universe · `4` does not reconcile |
| `test-ordinal-ratchet` | `-m ordinal_ratchet.cli . --json` | `0` nothing grew · `1` new collision or counter · `2` no universe / not comparable |
| `ts-py-anchor-guard` | `-m ts_py_anchor_guard.anchor_oracle --manifest <m> --json` | `0` conforming · `1` diverging · `2` not measured · `20` bad invocation |

`2` is mapped per instrument, not by convention: for `fiber-ast-lint` and `test-ordinal-ratchet`
it means *no subject* and becomes `NO_APLICABLE`; for the audit and the guard it means *could not
measure* and becomes `NO_MEDIDO`. An exit code no contract declares is `RC_NO_DECLARADO`, never a
guess.

A run whose instrument exits on a "measured" code without publishing its counters is
`SALIDA_SIN_HALLAZGOS_DECLARADOS` — not a zero. The reader that turned a missing list into an
empty one was the first bug this repository found in itself, and the `medido_es_numero` law below
is what caught it.

## The triage, and the reasons it publishes

Before any subprocess, the subject is read once — manifests, languages, test files, whether it is
a git tree — and each instrument is admitted or refused **by name**:

| reason | refused when |
|---|---|
| `SIN_ARBOL_GIT` | the subject is not a git work tree (`git-complement-audit`) |
| `SIN_SUPERFICIE_PYTHON` | no `.py` file, tests included (`fiber-ast-lint`) |
| `SIN_ARCHIVOS_DE_PRUEBA` | no test file matched (`test-ordinal-ratchet`) |
| `SIN_SUPERFICIE_TYPESCRIPT` | no `.ts`/`.tsx` (`ts-py-anchor-guard`) |
| `SIN_MANIFIESTO_DE_ANCLA` | TypeScript but no `ts-py-anchor.json` or equivalent |

`--forzar-todos` skips the gate and runs all four. It exists to measure what the gate saves; it is
not for publishing a check.

## The receipt

`--json` writes the canonical form: sorted keys, `ensure_ascii=False`, two-space indent, one
trailing newline, and `sello` = `sha256` over that form without the seal. Every executor carries
its own identity — `version`, `commit` of its repository, and `huella`, a `sha256` over its
package's `.py` files by relative path and content. Four laws are checked over the body:

| law | what it refuses |
|---|---|
| `particion` | applicable + not applicable + not measured + not executed must equal the instrument count |
| `identidad_de_ejecutores` | an `APLICABLE` row without version, commit and digest |
| `medido_es_numero` | an `APLICABLE` row whose findings are `null` |
| `estado_sin_medicion_nombra_su_razon` | any state other than `APLICABLE` with an empty reason |

A receipt that fails its own seal or its laws exits `3`, and nothing below it is worth reading.

### Determinism

No timestamp anywhere; `PYTHONHASHSEED=0`; `PYTHONDONTWRITEBYTECODE=1` so the runner never leaves a
`__pycache__` inside an instrument's checkout; every environment variable not on the allowlist
dropped; every list sorted; no absolute path in the receipt (the subject's path and `--raiz` are
masked as `<sujeto>` and `<herramientas>`). Two runs over one tree must produce the same bytes:

```
frontera-runner /ruta/sujeto --json --recibo uno.json >/dev/null
frontera-runner /ruta/sujeto --json --recibo dos.json >/dev/null
cmp uno.json dos.json && echo "byte-identical"
```

Masking is what makes the seal portable, not just stable: the same tree copied to
`/tmp/clon-uno` and to `/tmp/clon-dos-con-nombre-mas-largo` (2 files, 1 test, no `.git`) produced
one seal, `sha256:d1c706c5e55b5…497`, from both paths.

### Exit codes of the runner

| code | meaning |
|---|---|
| `0` | at least one instrument measured, all measured clean |
| `1` | measured, with findings: actionable |
| `2` | nothing measurable (`SIN_SUPERFICIE`) or a hole in the measurement (`HUECO_DE_MEDICION`) |
| `3` | the receipt failed its own seal or laws: not a verdict about the subject |
| `20` | bad invocation |

`2` outranks `1` in the sense that an unmeasured row is never read as a clean one; a finding still
exits `1`.

## The age partition travels with the audit row

`git-complement-audit` dates every row it reports by the newest ref tip whose tree still holds that
path with that content, and partitions the refs into `<= 30 d`, `31–90 d`, `> 90 d`. A raw count of
"refs outside `HEAD`" invites the answer *those are old branches from years ago*, which is not an
answer to *what is still moving*. The composite receipt carries the partition:

```
paths_fuera_de_head=1 · blobs_fuera_de_head=1 · refs=2 · refs_vivas_30d=2 · refs_recientes_90d=0
· refs_inactivas=0 · refs_sin_fecha=0 · filas_vivas_30d=1 · filas_recientes_90d=0
· filas_inactivas=0 · filas_solo_historia=0 · estratos_reconcilian=sí
```

When the instrument does not publish the partition, those keys are `NO_MEDIDO` — never `0`.

## Measured, on four hand-built subjects

Every number below comes from running the four real instruments from their own checkouts
(`--raiz /Users/marlene`), twice per subject, on 2026-11-27. The subjects were deleted afterwards.

| subject | surface | rc | states | Markdown | two runs |
|---|---|---|---|---|---|
| `fs-a` — TS + Python + tests, and one branch left outside `HEAD` | 6 files · py 3 · tests 2 · ts 1 | `1` | 4 applicable, 1 with findings | 3 175 B | byte-identical |
| `fs-b` — the same tree, nothing outside `HEAD` | 6 files · py 3 · tests 2 · ts 1 | `0` | 4 applicable | 3 167 B | byte-identical |
| `fs-c` — Python only, not a git tree | 1 file · py 1 · tests 0 · ts 0 | `0` | 1 applicable · 3 `NO_APLICABLE` | 2 087 B | byte-identical |
| `fs-d` — a git tree with no files | 0 files | `0` | 1 applicable · 3 `NO_APLICABLE` | 2 755 B | byte-identical |

`fs-c` and `fs-d` are the case the whole repository is about: without the gate, both exit `2`
because an instrument that cannot run is a hole. With it, the two refusals are named and the verdict
is `0`.

### What the triage actually saves

Median of five runs, same machine, `--json` only, two separate sessions. Wall clock on a shared
laptop: read the ratio, not the absolute seconds.

| subject | triaged | `--forzar-todos` | saved | instruments skipped |
|---|---|---|---|---|
| `fs-a` (all four applicable) | 1.488 s | 1.643 s | 9.4 % | 0 |
| `fs-c` (one applicable) | 0.875 s | 1.536 s | 43.1 % | 3 |
| `fs-d` (one applicable) | 1.155 s | 1.655 s | 30.2 % | 3 |

The same three subjects measured in an earlier session: `fs-a` 0.799 s vs 0.734 s (**−8.9 %**: the
gate cost 65 ms), `fs-c` 0.195 s vs 0.630 s (69.1 %), `fs-d` 0.466 s vs 0.788 s (40.8 %). `fs-a`
changes sign between the two sessions, and that is the honest reading: where the gate skips nothing,
its cost is noise around zero.

So the ≥ 40 % half of the hypothesis holds where the hypothesis was aimed — repositories without
surface, 30–69 % depending on load — and is falsified as a general claim: the saving equals the cost
of the instruments the gate skips. Three subjects measured before those (a Python tree with tests,
the audit's own checkout, the ratchet's own checkout) saved 0–8 %.

## Tests

Standard library only, thirty-three tests, four fake instruments written to a temporary `--raiz` so
the subprocess boundary is exercised rather than mocked:

```
/opt/homebrew/bin/python3.14 -m unittest discover -s tests
/opt/homebrew/bin/python3.14 -m frontera_runner --self-test
```

The fakes answer through `<subject>/.fake/<instrument>.json`, because the environment is allowlisted
and the subject is the only channel the runner leaves open on purpose. The suite covers the triage
refusals, the entire exit-code mapping including the `2` trap, a crashing instrument, a timeout, a
missing instrument, seal recomputation and tamper detection, byte identity across two runs,
`NO_MEDIDO` where the instrument omitted its counters, and the 65 536-character cut.

## Boundaries

- **No imports of instrument internals.** Everything is a subprocess with a declared command. An
  instrument that only works from its own working directory fails here instead of passing quietly.
- **No writes into an instrument's repository.** `PYTHONDONTWRITEBYTECODE=1`, no baseline rewriting,
  nothing but reads.
- **Its own repository.** This runner is not vendored into any instrument; `--raiz` points at the
  directory where the four clones are siblings, and defaults to the parent of this repository.
- **Zero third-party dependencies.** Standard library only, Python 3.11 or newer (`tomllib`).

## License

MIT.
