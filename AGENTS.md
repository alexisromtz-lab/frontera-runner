# AGENTS.md — working in this repository

Rules for any agent or human changing this code. Short, and each one is checked by the
self-test or the contract tests. Numbers quoted here are printed by the command beside them.

## What this repository is

One CLI: run four boundary instruments over a subject, decide **before** running which of them
have a universe at all, and emit one sealed receipt plus a bounded Markdown block for a pull
request. Then compare two receipts (`diff`) so that the seal has a consumer. Nothing else. No
daemon, no server, no network client, no plugin system, no storage.

The four instruments live in their own repositories and are **not** dependencies of this one.
This repo knows them only by their command line and their JSON.

## Invariants (breaking one is a bug, not a tradeoff)

1. **Zero third-party dependencies.** Standard library only. `pyproject.toml` has
   `dependencies = []` and it stays that way. Check: every import in `frontera_runner/` is
   either `__future__`, a standard-library module (`argparse`, `hashlib`, `json`, `os`,
   `platform`, `re`, `subprocess`, `sys`, `tomllib`, `typing`) or a sibling `.` module.
2. **Never import an instrument.** Each one is invoked as `python -m …` in a subprocess with
   `cwd` at the subject. Importing `git_complement_audit`, `fiber_ast_lint`,
   `ordinal_ratchet` or `ts_py_anchor_guard` couples this repo to internals that change in
   other tabs' merge windows. Check: `tests/test_frontera.py` runs against four fakes installed
   as ordinary modules on `PYTHONPATH`; nothing else is imported.
3. **Never write into an instrument's checkout.** The runner writes only what the caller asks
   for (`--json`, `--md`, `--recibo`), always outside the subject. Check:
   `ENTORNO_PERMITIDO` pins `PYTHONDONTWRITEBYTECODE=1` and the smoke subjects run twice with
   no diff.
4. **Exit codes are a contract**: `0` clean, `1` findings, `2` nothing was measured, `3` the
   receipt is inconsistent (seal or law fails), `20` bad invocation. Never invent a sixth code.
   Never return `0` when a pass did not run. Check: `recibo.salida_global`, and
   `LineaDeComandos` in the tests.
5. **`NO_APLICABLE` is not zero.** An instrument that was not run because it has no universe is
   published as `NO_APLICABLE` with its reason, and never as `hallazgos: 0`. The triage reasons
   in `triaje_frontera.PATRONES_*`/`triar()` are contract: adding a reason is a schema change,
   and it needs a test that prints it. Check: `estado_sin_medicion_nombra_su_razon` and
   `medido_es_numero` in `leyes()`, both falsified by the tests.
6. **The five laws hold on every receipt.** Partition (every executor is in exactly one state
   and the counts sum to the instrument count), executor identity (version + digest for each, plus
   commit unless `procedencia` is `PAQUETE`), measured-is-a-number (a `rc` we accepted carries
   counters or says why not), findings-are-named (`hallazgos` equals the size of the identity
   census, and the census is what `diff` subtracts), and no-unmeasured-state-without-a-reason.
   `verificar()` recomputes them from the body; a receipt whose body was edited afterwards must not
   re-seal. Check: `--self-test` prints
   `sello recompone: True · cuerpo alterado no recompone: True`.
7. **Count and census cannot diverge.** `hallazgos` is `len(census)`, never the instrument's own
   counter: a row that cannot be named is `SALIDA_SIN_IDENTIDADES`, and a census whose size
   disagrees with the declared counter is `IDENTIDADES_NO_RECONCILIAN`. Adding an instrument means
   teaching `instrumentos._*_identidades` what one finding *is* for it first, and a unit that is not
   a finding (`ts-py-anchor-guard` counts pairs) declares `unidad` and its own `reconciliar`.
8. **The comparison is the consumer, and its precedence is data.** `diff` verifies both seals and
   both sets of laws before reading a single executor (`3`), then refuses a measurement that
   disappeared (`PERDIDA_DE_MEDICION`), an instrument that never answered on either side
   (`MEDICION_NO_HECHA`) and a delta produced by different bytes (`DELTA_NO_ATRIBUIBLE`) as `2`,
   then reports new findings as `1` — including the findings on a surface that base answered
   `NO_APLICABLE` and head actually measured (`SUPERFICIE_NUEVA`): filling an absence is not the
   same as finding a hole. A base that never measured (`SIN_BASE_MEDIDA`) withdraws attribution and
   stays `0` by default; `--estricto-base` reads the same delta as `2` for a frozen route. A
   resolved finding never fires the gate, and a lost measurement is never credited as one.
   The pair *note → counter → exit code* lives only in `recibo.NOTAS`, and `_nota()` refuses to
   write a note with no row: a note nobody counts used to be exactly how one false green was born.
   The same row carries the paragraph the comment shows (`detalle`, `None` when a note owes none),
   so `render` never compares `fila["nota"]` against a literal, and `validar_notas()` refuses an
   incomplete row at import. Check: `ConsumidorDiferencial` (nine state pairs) and
   `CatalogoDeNotas`.
9. **A digest is only taken over a tree that holds still.** `huella_de_arbol` retries a walk whose
   files moved under it and answers `null` if they keep moving; `os.walk`'s silence about a
   directory it cannot list is turned into a retry, never into a smaller digest. Check:
   `Huellas::test_una_huella_no_se_toma_sobre_un_arbol_que_se_esta_escribiendo` and
   `Huellas::test_un_subarbol_que_desaparece_no_se_omite_en_silencio`.

10. **Determinism, not approximate determinism.** No timestamps anywhere; `PYTHONHASHSEED=0`;
   sorted keys and sorted lists; the reference date of age strata is a commit date, never the
   clock. Check: `--self-test` prints `dos corridas byte-idénticas: True`, and the four smoke
   subjects were each run twice with identical bytes.
11. **No absolute paths in the receipt.** Paths are masked to `<sujeto>` and `<herramientas>`.
   A receipt from one machine must be comparable with the same subject on another.
12. **Markdown is bounded.** `render.TOPE = 65_536` is the ceiling of a PR comment / Check Run.
   Over it, `recortar()` cuts and says it cut. A silent truncation is a false green.
13. **The interpreter is declared.** The digest of the code does not name the runtime, so
    `interprete` travels in the receipt. The runner passes `sys.executable` to every
    subprocess: one interpreter per run, never a mix.
14. **Numbers in `README.md` come from a stated command.** Each table names the subject and the
    invocation. The four smoke subjects were hand-built in `/tmp` and are described well enough
    to rebuild them; the tests use fakes and their numbers are properties, not measurements.
    Never quote a measurement taken from a private repository.

## Verification, before any commit

```bash
python -m frontera_runner.cli --self-test              # 3 properties, RC 0
python -m unittest discover -s tests                   # 52 tests, RC 0
```

Both must pass. A change that does not move any test is suspect: state why in the commit
message. The suite spawns subprocesses for the fakes, so it takes ~70 s wall. The fixture commits
are pinned to a fixed date: a commit digest that moved with the clock would make the byte-identity
tests pass or fail depending on the second they ran in.

## Changing the triage

`superficie()` measures the subject once (files, Python, tests, TypeScript, anchor manifests,
excluded directories, git tree) and `triar()` maps the absent ones to a reason per instrument.
The gate is allowed to be wrong about saving time — the measured savings are 69.1 % and 40.8 %
where surface is absent, and negative where it is not — but it is not allowed to be wrong about
correctness: an instrument is skipped only when its own universe is provably empty, and the
reason is printed in the table, the JSON and the Markdown.

## Adding an instrument

One `Instrumento` in `instrumentos.INSTRUMENTOS`: module, package (for version and digest),
arguments, the rc contract, and where in its JSON the denominator and the finding count live.
Then an `identidades` extractor that names one finding, and a fake in `tests/apoyo.py` whose
payload publishes those names — a fake that publishes counters without detail is now correctly
read as `SALIDA_SIN_IDENTIDADES`. If the new JSON shape has no counters, the receipt will say
`SALIDA_SIN_HALLAZGOS_DECLARADOS` until you teach `_denominador` to read it — and that is the
honest answer, not a bug to paper over.
