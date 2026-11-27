"""Read the subject before running anything: what surface does it actually have?

Triage exists for one reason: an instrument invoked on a subject it cannot read returns its
"no universe" code, and a composite that folds that code into "0 findings" publishes a green
about bytes nobody looked at. So the gate runs first, refuses what the subject cannot support,
and says which instrument it refused and why. A refusal is `NO_APLICABLE` with a reason --
never a zero.

Triage is deliberately permissive: it refuses only when the surface is provably absent, and
the instrument's own "no universe" code still wins if the two disagree, because the instrument
measured and triage only looked.
"""

from __future__ import annotations

import os
import subprocess
from typing import Iterable, Mapping

#: Directories that are not the subject's own code. Declared, because the denominator of every
#: count below is "files walked minus these", and a hidden exclusion is a quieter report.
EXCLUSIONES = (
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "target",
    "vendor",
    "site-packages",
)

#: Test-file spellings the ordinal ratchet reads by default, plus the one it needs declared.
PATRONES_PRUEBA = ("test_*.py", "*_test.py")

#: Manifest names the anchor guard can be pointed at, in preference order. A guard run needs a
#: signed correspondence; without it the instrument reports "no evaluable anchor", not a zero.
CANDIDATOS_MANIFIESTO = ("ts-py-anchor.json", "frontera-anclas.json", "anclas.json")

SUFIJOS_TYPESCRIPT = (".ts", ".tsx")


def _archivos(sujeto: str) -> Iterable[str]:
    """Every regular file under `sujeto`, relative, sorted, minus the declared exclusions."""
    for raiz, dirs, nombres in os.walk(sujeto):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUSIONES)
        for nombre in sorted(nombres):
            ruta = os.path.join(raiz, nombre)
            if os.path.islink(ruta) or not os.path.isfile(ruta):
                continue
            yield os.path.relpath(ruta, sujeto)


def _es_prueba(nombre: str) -> bool:
    return nombre.startswith("test_") and nombre.endswith(".py") or nombre.endswith("_test.py")


def _es_typescript(nombre: str) -> bool:
    if nombre.endswith(".d.ts"):
        return False
    return nombre.endswith(SUFIJOS_TYPESCRIPT)


def es_arbol_git(sujeto: str) -> bool:
    """Whether `sujeto` is inside a git work tree. Read-only: `rev-parse`, no discovery writes."""
    try:
        hecho = subprocess.run(
            ["git", "-C", sujeto, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return hecho.returncode == 0 and hecho.stdout.strip() == "true"


def superficie(sujeto: str) -> dict:
    """What the walk saw. Counts are of files, not of bytes, and the walk is declared."""
    python = pruebas = typescript = 0
    manifiestos = []
    leidos = 0
    for rel in _archivos(sujeto):
        leidos += 1
        nombre = os.path.basename(rel)
        if nombre.endswith(".py"):
            python += 1
            if _es_prueba(nombre):
                pruebas += 1
        elif _es_typescript(nombre):
            typescript += 1
        if rel in CANDIDATOS_MANIFIESTO:
            manifiestos.append(rel)
    return {
        "archivos": leidos,
        "python": python,
        "pruebas": pruebas,
        "typescript": typescript,
        "manifiestos_ancla": manifiestos,
        "exclusiones": list(EXCLUSIONES),
        "arbol_git": es_arbol_git(sujeto),
    }


def triar(sujeto: str, sup: Mapping | None = None) -> dict:
    """Per instrument: `APLICABLE`, or `NO_APLICABLE` with the reason the surface is absent."""
    sup = dict(sup or superficie(sujeto))
    triaje = {}

    def poner(nombre: str, falta: str | None, insumos: Mapping | None = None) -> None:
        if falta is None:
            triaje[nombre] = {"estado": "APLICABLE", "razon": "", "insumos": dict(insumos or {})}
        else:
            triaje[nombre] = {"estado": "NO_APLICABLE", "razon": falta, "insumos": dict(insumos or {})}

    poner("git-complement-audit", None if sup["arbol_git"] else "SIN_ARBOL_GIT",
          {"arbol_git": sup["arbol_git"]})
    poner("fiber-ast-lint", None if sup["python"] else "SIN_SUPERFICIE_PYTHON",
          {"python": sup["python"]})
    poner("test-ordinal-ratchet", None if sup["pruebas"] else "SIN_ARCHIVOS_DE_PRUEBA",
          {"pruebas": sup["pruebas"]})
    if not sup["typescript"]:
        falta, insumos = "SIN_SUPERFICIE_TYPESCRIPT", {"typescript": 0}
    elif not sup["manifiestos_ancla"]:
        falta, insumos = "SIN_MANIFIESTO_DE_ANCLA", {"typescript": sup["typescript"]}
    else:
        falta, insumos = None, {"typescript": sup["typescript"],
                                "manifiesto": sup["manifiestos_ancla"][0]}
    poner("ts-py-anchor-guard", falta, insumos)
    return triaje
