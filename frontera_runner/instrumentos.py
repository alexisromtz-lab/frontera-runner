"""The four instruments, declared once: how to call each, and how to read what it says.

Three of the four return `2` for "no universe to measure" and one returns `4` for "the run does
not reconcile". Those codes are the whole reason a composite runner has to know its colleagues:
folding `2` into "0 findings" turns an empty universe into a green, which is the defect this
repository exists to not commit. The mapping below is the contract, and every code a run can
emit is either mapped or reported as `RC_NO_DECLARADO` -- never guessed.

Nothing here imports an instrument. They are called as subprocesses, from their own repository,
with the subject as the working directory, so an instrument that only works from its own cwd
fails loudly here instead of quietly passing.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from typing import Callable, Mapping

SIN_HALLAZGOS = "SIN_HALLAZGOS"
CON_HALLAZGOS = "CON_HALLAZGOS"
SIN_SUJETO = "SIN_SUJETO"
NO_MEDIDO = "NO_MEDIDO"


@dataclass(frozen=True)
class Instrumento:
    """One colleague: where it lives, how to call it, and what its exit codes mean."""

    nombre: str
    modulo: str
    paquete: str
    argumentos: tuple[str, ...]
    rc_contrato: Mapping[int, tuple[str, str]]
    denominador: Callable[[Mapping], dict]
    hallazgos: Callable[[Mapping], int | None]
    subruta: str = ""

    def ruta_python(self, repo: str) -> str:
        """Where the package must be put on `PYTHONPATH` -- a `src/` layout is not optional."""
        return os.path.join(repo, self.subruta) if self.subruta else repo

    def comando(self, manifiesto: str | None = None) -> list[str]:
        return [self.modulo, *[a.format(manifiesto=manifiesto or "") for a in self.argumentos]]


def _suma(claves: tuple[str, ...], salida: Mapping) -> int | None:
    try:
        return sum(int(salida[k]) for k in claves)
    except (KeyError, TypeError, ValueError):
        return None


def _auditoria_denominador(salida: Mapping) -> dict:
    """The universe *and* its age partition: a count of refs nobody dates is not actionable.

    The partition travels in the composite receipt because a raw total invites the answer
    "those are old branches from years ago", which is not an answer to "what is still moving".
    """
    universo = salida.get("universe") or {}
    estratos = salida.get("age_strata") or {}
    refs = estratos.get("refs") or {}
    return {"paths_fuera_de_head": universo.get("paths"),
            "blobs_fuera_de_head": universo.get("blobs_outside_head"),
            "refs": (salida.get("repo") or {}).get("refs"),
            "refs_vivas_30d": refs.get("live"),
            "refs_recientes_90d": refs.get("recent"),
            "refs_inactivas": refs.get("stale"),
            "refs_sin_fecha": refs.get("undated"),
            "filas_vivas_30d": estratos.get("live"),
            "filas_recientes_90d": estratos.get("recent"),
            "filas_inactivas": estratos.get("stale"),
            "filas_solo_historia": estratos.get("history_only"),
            "estratos_reconcilian": estratos.get("conservation")}


def _guardia_denominador(salida: Mapping) -> dict:
    totales = salida.get("totales") or {}
    return {"pares": totales.get("pares"),
            "anclas_comparadas": totales.get("comparadas"),
            "anclas_declaradas": totales.get("declaradas")}


def _fibras_denominador(salida: Mapping) -> dict:
    return {"archivos_python": salida.get("archivos"),
            "sitios_medidos": salida.get("for_medidos")}


def _ordinal_denominador(salida: Mapping) -> dict:
    return {"archivos_de_prueba": salida.get("files"),
            "archivos_leidos": salida.get("parsed")}


INSTRUMENTOS: tuple[Instrumento, ...] = (
    Instrumento(
        nombre="git-complement-audit",
        modulo="git_complement_audit",
        paquete="git_complement_audit",
        argumentos=(".", "--json"),
        rc_contrato={
            0: (SIN_HALLAZGOS, "existe solo lo que HEAD alcanza"),
            1: (CON_HALLAZGOS, "codigo huerfano o riesgo de secreto"),
            2: (NO_MEDIDO, "repositorio o argumentos invalidos"),
        },
        denominador=_auditoria_denominador,
        hallazgos=lambda s: _suma(("ORPHAN_CODE", "ORPHAN_SECRET_RISK", "HISTORY_SECRET_RISK"),
                                  s.get("counts") or {}),
    ),
    Instrumento(
        nombre="fiber-ast-lint",
        modulo="fiber_ast_lint.cli",
        paquete="src/fiber_ast_lint",
        subruta="src",
        argumentos=(".", "--json"),
        rc_contrato={
            0: (SIN_HALLAZGOS, "ningun candidato"),
            1: (CON_HALLAZGOS, "candidatos a revisar"),
            2: (SIN_SUJETO, "universo vacio: ningun archivo Python analizado"),
            4: (NO_MEDIDO, "el instrumento no reconcilia"),
        },
        denominador=_fibras_denominador,
        # An empty list is a measurement; a missing key is not, and `or []` would blur them.
        hallazgos=lambda s: len(s["candidatos"]) if isinstance(s.get("candidatos"), list) else None,
    ),
    Instrumento(
        nombre="test-ordinal-ratchet",
        modulo="ordinal_ratchet.cli",
        paquete="ordinal_ratchet",
        argumentos=(".", "--json"),
        rc_contrato={
            0: (SIN_HALLAZGOS, "nada crecio sobre la linea base declarada"),
            1: (CON_HALLAZGOS, "colision nueva, contador sobre la linea base o deuda desaparecida"),
            2: (SIN_SUJETO, "sin archivo de prueba, nada parsea, o no comparable"),
        },
        denominador=_ordinal_denominador,
        hallazgos=lambda s: _suma(("ordinal", "shadow", "shared"), s.get("total") or {}),
    ),
    Instrumento(
        nombre="ts-py-anchor-guard",
        modulo="ts_py_anchor_guard.anchor_oracle",
        paquete="ts_py_anchor_guard",
        argumentos=("--manifest", "{manifiesto}", "--json"),
        rc_contrato={
            0: (SIN_HALLAZGOS, "anclas conformes"),
            1: (CON_HALLAZGOS, "alguna ancla diverge"),
            2: (NO_MEDIDO, "no medido: ancla no evaluable, cobertura incompleta o insumo ilegible"),
            20: (NO_MEDIDO, "invocacion invalida"),
        },
        denominador=_guardia_denominador,
        hallazgos=lambda s: _suma(("divergen", "no_medidos"), s.get("totales") or {}),
    ),
)

POR_NOMBRE = {i.nombre: i for i in INSTRUMENTOS}


def version_de(repo: str, paquete: str = "") -> str | None:
    """The version the instrument declares: its `pyproject.toml`, or its `__init__.py`.

    Both spellings exist in the four: three pin the version in the packaging metadata and one
    keeps it in the package and lets the metadata read it dynamically. A reader that knows only
    the first reports `NO_MEDIDO` for a version that is written down and easy to find.
    """
    try:
        with open(os.path.join(repo, "pyproject.toml"), "rb") as f:
            datos = tomllib.load(f)
        version = (datos.get("project") or {}).get("version")
        if version is not None:
            return str(version)
    except (OSError, tomllib.TOMLDecodeError):
        pass
    for candidato in (os.path.join(paquete, "__init__.py") if paquete else "__init__.py",
                      "__init__.py"):
        try:
            with open(os.path.join(repo, candidato), encoding="utf-8") as f:
                match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', f.read(), re.MULTILINE)
        except OSError:
            continue
        if match:
            return match.group(1)
    return None


def commit_de(repo: str) -> str | None:
    """`HEAD` of the instrument's repository: the tree that ran, not the one it claims."""
    try:
        hecho = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                               capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return hecho.stdout.strip() or None if hecho.returncode == 0 else None


def huella_de(repo: str, paquete: str) -> str | None:
    """`sha256:` over the package's `.py` files, path and content, in sorted order.

    A commit names the tree and the version names the release; neither names the bytes that
    ran if someone edited a checkout. This digest does, and it is taken over relative paths so
    it survives being cloned somewhere else.
    """
    raiz = os.path.join(repo, paquete)
    if not os.path.isdir(raiz):
        return None
    archivos = []
    for actual, dirs, nombres in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for nombre in sorted(nombres):
            if nombre.endswith(".py"):
                archivos.append(os.path.join(actual, nombre))
    if not archivos:
        return None
    resumen = hashlib.sha256()
    for ruta in sorted(archivos, key=lambda r: os.path.relpath(r, raiz).replace(os.sep, "/")):
        rel = os.path.relpath(ruta, raiz).replace(os.sep, "/")
        resumen.update(rel.encode("utf-8") + b"\0")
        with open(ruta, "rb") as f:
            resumen.update(hashlib.sha256(f.read()).digest())
    return "sha256:" + resumen.hexdigest()


def identificar(repo: str, instrumento: Instrumento) -> dict:
    return {
        "version": version_de(repo, instrumento.paquete),
        "commit": commit_de(repo),
        "huella": huella_de(repo, instrumento.paquete),
    }
