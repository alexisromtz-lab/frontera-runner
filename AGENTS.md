# AGENTS.md — working in this repository

Rules for any agent or human changing this code. Short, and each one is checked by the
self-test or the contract tests. Numbers quoted here are printed by the command beside them.

## What this repository is

One CLI: run four boundary instruments over a subject, decide **before** running which of them
have a universe at all, and emit one sealed receipt plus a bounded Markdown block for a pull
request. Nothing else. No daemon, no server, no network client, no plugin system, no storage.

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
6. **The four laws hold on every receipt.** Partition (every executor is in exactly one state
   and the counts sum to the instrument count), executor identity (version + commit + digest
   for each), measured-is-a-number (a `rc` we accepted carries counters or says why not), and
   no-unmeasured-state-without-a-reason. `verificar()` recomputes them from the body; a receipt
   whose body was edited afterwards must not re-seal. Check: `--self-test` prints
   `sello recompone: True · cuerpo alterado no recompone: True`.
7. **Determinism, not approximate determinism.** No timestamps anywhere; `PYTHONHASHSEED=0`;
   sorted keys and sorted lists; the reference date of age strata is a commit date, never the
   clock. Check: `--self-test` prints `dos corridas byte-idénticas: True`, and the four smoke
   subjects were each run twice with identical bytes.
8. **No absolute paths in the receipt.** Paths are masked to `<sujeto>` and `<herramientas>`.
   A receipt from one machine must be comparable with the same subject on another.
9. **Markdown is bounded.** `render.TOPE = 65_536` is the ceiling of a PR comment / Check Run.
   Over it, `recortar()` cuts and says it cut. A silent truncation is a false green.
10. **The interpreter is declared.** The digest of the code does not name the runtime, so
    `interprete` travels in the receipt. The runner passes `sys.executable` to every
    subprocess: one interpreter per run, never a mix.
11. **Numbers in `README.md` come from a stated command.** Each table names the subject and the
    invocation. The four smoke subjects were hand-built in `/tmp` and are described well enough
    to rebuild them; the tests use fakes and their numbers are properties, not measurements.
    Never quote a measurement taken from a private repository.

## Verification, before any commit

```bash
python -m frontera_runner.cli --self-test              # 3 properties, RC 0
python -m unittest discover -s tests                   # 33 tests, RC 0
```

Both must pass. A change that does not move any test is suspect: state why in the commit
message. The suite spawns subprocesses for the fakes, so it takes ~25 s wall and ~8 s user.

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
Then the four-state mapping in `runner.ejecutar` and a fake in `tests/apoyo.py`. If the new JSON
shape has no counters, the receipt will say `SALIDA_SIN_HALLAZGOS_DECLARADOS` until you teach
`_denominador` to read it — and that is the honest answer, not a bug to paper over.
