# frontera-runner

One subject in. One sealed receipt out. Four instruments that live in four other repositories,
called as subprocesses, never imported.

The point is not to run four linters. The point is to publish **one** verdict a pull request can
read, in which an instrument that had nothing to measure says so by name instead of returning a
green zero.

```
frontera-runner <sujeto>                                 # Markdown for a PR check
frontera-runner <sujeto> --json                          # the canonical receipt
frontera-runner diff --base b.json --head h.json         # the gate: what the PR changed
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

## Findings are counted from their names, not from a counter

Every accepted payload is read twice: once for the number the instrument declares, and once for a
census of the findings themselves. The census is built from the payload's own detail lists and each
row that cannot be named is `SALIDA_SIN_IDENTIDADES`; a census whose size disagrees with the
declared counter is `IDENTIDADES_NO_RECONCILIAN`. Both are `NO_MEDIDO` with a reason, never a
number somebody typed. `hallazgos` in the receipt is `len(census)` — the identity list is what the
`diff` subtracts, so it must be the thing that was counted.

| instrument | identity of one finding |
|---|---|
| `git-complement-audit` | `class｜path｜root` |
| `fiber-ast-lint` | `archivo｜qualname｜familia｜forma｜poblacion` |
| `test-ordinal-ratchet` | `kind｜path｜scope｜name` |
| `ts-py-anchor-guard` | `DIVERGE｜par｜ancla` (its unit is the **pair**, see below) |

Two deliberate omissions: the audit's identity carries no `oid`/`size` (a finding that moved
object is the same finding at the same path) and the fibre's carries no line number (a finding that
shifted lines is not a new finding). Line numbers and object ids are precisely what a pull request
changes without changing the defect.

The guard is the exception that shaped the design: it rolls `divergen` up **per pair**, not per
anchor, so a per-anchor census would fail to reconcile against a correct instrument. Its
reconciliation is therefore a partition — every pair is named exactly once, and a pair is in the
diverging set if and only if it is not clean. A pair that reports `rc: 0` while naming a broken
anchor is `IDENTIDADES_NO_RECONCILIAN`, which is how a self-contradictory payload is caught instead
of being read as a clean run.

## Where the instruments are found: two routes, and a promise

| route | when | `procedencia` | `commit` |
|---|---|---|---|
| `CLON` | `--raiz` names a directory of sibling checkouts, or they sit next to this repository | `CLON` | measured with `git rev-parse` |
| `PAQUETE` | no `--raiz`, no sibling, but the module is importable by this interpreter | `PAQUETE` | `null`: an installation has no history to read |

`--raiz` is a promise. Passing it means *measure exactly these checkouts*, so a missing sibling is
`INSTRUMENTO_AUSENTE` and an installed copy is never substituted for the tree that was asked about.
Omitting it means *find them*, which is the only route a consumer repository has: it has no four
sibling clones, and it installs the instruments into the environment instead.

A pin (`--pines archivo.json`, `{"instrumento": {"commit": …, "version": …}}`) is a **declaration**
and never a measurement. In `CLON` it is checked against the commit that was read (`VERIFICADO` /
`DIVERGE`); in `PAQUETE` it cannot be, and the row says `NO_VERIFICABLE` rather than claiming a
agreement it did not observe.

What makes the two routes comparable is the digest: `huella` is taken over the package's `.py`
files by **relative** path and content, so the same bytes installed under `site-packages/` and
checked out under `src/` seal identically. Measured on 2026-11-28 over the four instruments at
`git-complement-audit@1c73546`, `fiber-ast-lint@753a951`, `test-ordinal-ratchet@36e8b27`,
`ts-py-anchor-guard@02e8fe3`: **four of four huellas equal** between the installed and the checked
out copy, and the generator's huella equal too. Only `procedencia` and `commit` differ.

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
its own identity — `version`, `commit` of its repository (`null` when installed), `huella`, a
`sha256` over its package's `.py` files by relative path and content, and `procedencia`. Five laws
are checked over the body (`schema: 2`):

| law | what it refuses |
|---|---|
| `particion` | applicable + not applicable + not measured + not executed must equal the instrument count |
| `identidad_de_ejecutores` | an `APLICABLE` row without version and digest, or without a commit unless it is `PAQUETE` |
| `medido_es_numero` | an `APLICABLE` row whose findings are `null` |
| `hallazgos_nombrados` | an `APLICABLE` row whose findings are not the size of its own identity list |
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

Measured again on 2026-11-28 with the **real** instruments instead of fakes, and with live `.git`
history on both sides: one subject cloned to `/tmp/inv/a` and to
`/tmp/inv/una/ruta/bastante/mas/profunda/b`, run in `PAQUETE` mode, produced the byte-identical
receipt `8b009823e3654804…5e4b8` from both paths, and the same seal again on a second consecutive
run. Path invariance is a property of the digest, not of the length of the directory name.

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

## The differential gate: `diff`

A seal nobody reads is decoration. In a pull request the reader is the comparison between the
receipt of `base.sha` and the receipt of `head.sha`:

```
frontera-runner diff --base recibo-base.json --head recibo-head.json --md comentario.md
```

The order of the checks is the contract, because each one makes the next meaningless:

1. **Both seals are recomputed before a single executor is read.** A body that no longer matches
   its own digest is a document somebody edited; what it says about findings does not matter.
   `SELLO_NO_RECOMPONE`. Both receipts must also close their laws (`LEYES_NO_CIERRAN`) and carry
   the schema this reader knows: two different schemas are `ESQUEMAS_DISTINTOS`, and a pair that
   agrees on an older schema is `RECIBO_NO_COMPARABLE` — a v1 receipt has no census to subtract.
2. **A measurement that disappeared is a loss, and a loss is never a resolution.** If an instrument
   was `APLICABLE` in base and is not in head — the pull request deleted the anchor manifest, say —
   the row is `PERDIDA_DE_MEDICION` with the count of findings that went unmeasured, and the gate
   exits `2`. Reading that as "0 findings, all fixed" is the false green this repository exists to
   refuse.
3. **An absence that the pull request fills is a surface the pull request creates.** When an
   instrument was `NO_APLICABLE` in base — "nothing of mine to measure" — and is `APLICABLE` in
   head, every finding on that new surface is the pull request's: the row is `SUPERFICIE_NUEVA`,
   `atribuible: true`, and the gate exits `1`. A hole is not the same thing: a base that answered
   `NO_MEDIDO` never measured, so its findings may predate the change and the row stays
   `SIN_BASE_MEDIDA` / `2`. Without this branch, adding the first TypeScript file next to a
   diverging Python port would read as `SIN_REGRESION`. <!-- medido: corrida 46076223056 -->
4. **A delta produced by different bytes is not about the pull request.** If an executor's
   `version`, `huella` or `procedencia` moved between the two receipts, the row is
   `DELTA_NO_ATRIBUIBLE` and contributes nothing either way. Bumping an instrument is therefore
   never silently green: `2`. Divergence needs two identities to diverge: a side that never ran
   publishes none, so the identity of a `NO_APLICABLE` side is not compared.
5. **Only then** the multiset difference of the identity lists: `nuevos` (in head, not in base)
   exits `1`; `resueltos` (in base, not in head) is reported and never fires the gate; nothing new
   exits `0`.

| code | meaning |
|---|---|
| `0` | `SIN_REGRESION` — no finding in head that was not in base |
| `1` | `REGRESION` — at least one new finding, named, including findings on a surface this PR created |
| `2` | `PERDIDA_DE_MEDICION`, `SIN_BASE_MEDIDA` or `DELTA_NO_ATRIBUIBLE` — the comparison stopped being about the PR |
| `3` | the receipt could not be read as a receipt: seal, laws or schema |
| `20` | bad invocation (a receipt path that does not parse) |

A finding that was already in base is not a regression, and a finding that appears because an
instrument got *stricter* is `DELTA_NO_ATRIBUIBLE` rather than a regression — the gate refuses to
attribute it and says why.

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

Standard library only, fifty-two tests, four fake instruments written to a temporary `--raiz` so
the subprocess boundary is exercised rather than mocked:

```
/opt/homebrew/bin/python3.14 -m unittest discover -s tests
/opt/homebrew/bin/python3.14 -m frontera_runner --self-test
```

The fakes answer through `<subject>/.fake/<instrument>.json`, because the environment is allowlisted
and the subject is the only channel the runner leaves open on purpose. The suite covers the triage
refusals, the entire exit-code mapping including the `2` trap, a crashing instrument, a timeout, a
missing instrument, seal recomputation and tamper detection, byte identity across two runs,
`NO_MEDIDO` where the instrument omitted its counters, and the 65 536-character cut. On top of
that, the `diff` contract (a receipt tampered with in one byte is `3`, a finding already in base is
not a regression, a deleted measurement is `2` and never "resolved", the guard's per-pair
partition), the two resolution routes, and path invariance: two clones of one subject at two depths,
two different `--raiz`, one seal — with the fixtures' commits pinned to a fixed date, because
otherwise the digest of a fake repository depends on the second it was created in.

## Boundaries

- **No imports of instrument internals.** Everything is a subprocess with a declared command. An
  instrument that only works from its own working directory fails here instead of passing quietly.
- **No writes into an instrument's repository.** `PYTHONDONTWRITEBYTECODE=1`, no baseline rewriting,
  nothing but reads.
- **Its own repository.** This runner is not vendored into any instrument. It finds them two ways
  and never mixes them: `--raiz` names sibling checkouts (default: the parent of this repository),
  and with no `--raiz` an absent sibling falls back to the package installed in this interpreter.
  An explicit `--raiz` that is missing an instrument is a hole, not a fallback.
- **Zero third-party dependencies.** Standard library only, Python 3.11 or newer (`tomllib`).

## License

MIT.
