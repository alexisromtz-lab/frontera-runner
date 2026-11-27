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
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from typing import Callable, Mapping

SIN_HALLAZGOS = "SIN_HALLAZGOS"
CON_HALLAZGOS = "CON_HALLAZGOS"
SIN_SUJETO = "SIN_SUJETO"
NO_MEDIDO = "NO_MEDIDO"

#: The audit classes whose count is the number the gate reads. The instrument also publishes
#: `ORPHAN_DOC`, `MOVED` and `RESIDUE`, which are informational: they never move its exit code
#: and counting them here would make a stale note block a merge.
CLASES_FALLANTES_AUDITORIA = ("ORPHAN_CODE", "ORPHAN_SECRET_RISK", "HISTORY_SECRET_RISK")

#: Separator inside one finding's identity. Every field is escaped with `_parte`, so the key can
#: be read back by splitting on a `|` that is genuinely a separator.
SEP = "|"

#: The guard's per-par exit codes, read from its payload rather than from the process.
_RC_DIVERGE = 1
_RC_NO_MEDIDO = 2


def _parte(valor) -> str:
    """One field of a finding's identity: single line, and never a `|` that splits the key."""
    return str(valor).replace("|", "%7C").replace("\n", " ")


def _clave(*campos) -> str | None:
    """Join the fields of one finding, or `None` when any of them is missing.

    A finding the runner cannot name is not a finding it may count: the two numbers would then
    disagree and the receipt would publish a delta over a census it cannot reconcile.
    """
    if any(c is None or c == "" for c in campos):
        return None
    return SEP.join(_parte(c) for c in campos)


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
    identidades: Callable[[Mapping], list[str] | None]
    subruta: str = ""
    #: The unit `hallazgos` counts in. Three instruments count findings; the guard counts pars.
    unidad: str = "hallazgo"
    #: How the named census is reconciled with the instrument's own count. `None` means
    #: "same number", which is right wherever the instrument counts what it lists.
    reconciliar: Callable[[Mapping, list[str]], bool] | None = None

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


def _auditoria_identidades(salida: Mapping) -> list[str] | None:
    """One name per failing finding: class, path, and the root it was found under.

    The oid and the size are left out on purpose. They change when the file at the same path
    changes, and "this path is not reachable from HEAD" is the defect either way; keeping them
    would report every edited orphan as one new finding plus one resolved one.
    """
    hallazgos = salida.get("findings")
    if not isinstance(hallazgos, list):
        return None
    nombres = []
    for hallazgo in hallazgos:
        if not isinstance(hallazgo, dict) or hallazgo.get("class") not in CLASES_FALLANTES_AUDITORIA:
            continue
        clave = _clave(hallazgo.get("class"), hallazgo.get("path"), hallazgo.get("root"))
        if clave is None:
            return None
        nombres.append(clave)
    return nombres


def _fibras_identidades(salida: Mapping) -> list[str] | None:
    """Candidate, file, function, family, shape and population -- not the line number.

    A line number is a position, not an identity: moving twenty lines above a candidate would
    otherwise read as one finding resolved and an unrelated one introduced.
    """
    lista = salida.get("candidatos")
    if not isinstance(lista, list):
        return None
    nombres = []
    for candidato in lista:
        if not isinstance(candidato, dict):
            return None
        clave = _clave(candidato.get("archivo"),
                       candidato.get("qualname") or candidato.get("funcion"),
                       candidato.get("familia"), candidato.get("forma"),
                       candidato.get("poblacion"))
        if clave is None:
            return None
        nombres.append(clave)
    return nombres


def _ordinal_identidades(salida: Mapping) -> list[str] | None:
    """Kind, file, scope and the name the collision was reported under."""
    lista = salida.get("collisions")
    if not isinstance(lista, list):
        return None
    nombres = []
    for colision in lista:
        if not isinstance(colision, dict):
            return None
        clave = _clave(colision.get("kind"), colision.get("path"),
                       colision.get("scope"), colision.get("name"))
        if clave is None:
            return None
        nombres.append(clave)
    return nombres


def _guardia_identidades(salida: Mapping) -> list[str] | None:
    """One name per broken or unmeasured anchor, inside the par that owns it.

    The census is built from what the par *says about its anchors*, not from the par's own exit
    code: that is what lets the partition below catch a payload that contradicts itself -- a par
    the counter calls clean while one of its anchors is marked broken is not reconcilable, and
    the runner has to say so instead of believing the friendlier of the two claims.
    """
    pares = salida.get("pares")
    if not isinstance(pares, list):
        return None
    nombres = []
    for par in pares:
        if not isinstance(par, dict) or par.get("nombre") in (None, ""):
            return None
        if par.get("rc") not in (0, _RC_DIVERGE, _RC_NO_MEDIDO):
            return None
        nombre = _parte(par.get("nombre"))
        rotas = [a.get("ancla") for a in par.get("anclas") or []
                 if isinstance(a, dict) and a.get("ok") is False]
        sueltas = [a.get("ancla") if isinstance(a, dict) else a
                   for a in par.get("no_evaluables") or []]
        for ancla in rotas:
            nombres.append(_clave("DIVERGE", nombre, ancla)
                           or _clave("DIVERGE", nombre, "SIN_ANCLA"))
        for ancla in sueltas:
            nombres.append(_clave("NO_MEDIDO", nombre, ancla)
                           or _clave("NO_MEDIDO", nombre, "SIN_ANCLA"))
        if par.get("rc") == _RC_DIVERGE and not rotas:
            nombres.append(_clave("DIVERGE", nombre, par.get("detalle") or "SIN_ANCLA"))
        if par.get("rc") == _RC_NO_MEDIDO and not sueltas:
            nombres.append(_clave("NO_MEDIDO", nombre, par.get("causa") or "SIN_CAUSA"))
    return nombres


def _guardia_reconcilia(salida: Mapping, identidades: list[str]) -> bool:
    """The guard counts *pars*, so the census is reconciled as a partition, not as a sum.

    `totales.divergen` is `sum(1 for p in pares if p["rc"] == RC_DIVERGE)`: one par with three
    broken anchors is one. Comparing that number with the named census would reject a correct
    instrument, so the law here is the partition instead -- every par the counter calls broken
    or unmeasured names at least one finding, and every par it calls clean names none.
    """
    pares = salida.get("pares")
    if not isinstance(pares, list):
        return False
    nombres = [p.get("nombre") if isinstance(p, dict) else None for p in pares]
    if any(not isinstance(n, str) or n == "" for n in nombres):
        return False
    if len({_parte(n) for n in nombres}) != len(nombres):
        return False
    con_hallazgo = {clave.split(SEP, 2)[1] for clave in identidades if clave}
    for par in pares:
        limpio = par.get("rc") == 0
        if limpio == (_parte(par["nombre"]) in con_hallazgo):
            return False
    return True


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
        hallazgos=lambda s: _suma(CLASES_FALLANTES_AUDITORIA, s.get("counts") or {}),
        identidades=_auditoria_identidades,
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
        identidades=_fibras_identidades,
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
        identidades=_ordinal_identidades,
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
        identidades=_guardia_identidades,
        unidad="par",
        reconciliar=_guardia_reconcilia,
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


def huella_de_arbol(raiz: str) -> str | None:
    """`sha256:` over a package's `.py` files, relative path and content, in sorted order.

    A commit names the tree and the version names the release; neither names the bytes that
    ran if someone edited a checkout. This digest does, and it is taken over relative paths so
    it survives the same package being installed somewhere else.
    """
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
        resumen.update(rel.encode("utf-8") + b"\x00")
        with open(ruta, "rb") as f:
            resumen.update(hashlib.sha256(f.read()).digest())
    return "sha256:" + resumen.hexdigest()


def huella_de(repo: str, paquete: str) -> str | None:
    """The digest of the package inside a checkout: `<repo>/<paquete>`."""
    return huella_de_arbol(os.path.join(repo, paquete))


#: Asked in a subprocess on purpose: locating an installed package must not become importing it,
#: and this package's whole isolation argument is that no instrument ever runs in this process.
_SONDEO_INSTALADO = """\
import importlib.metadata, importlib.util, json
especificacion = importlib.util.find_spec({paquete!r})
if especificacion is None:
    print(json.dumps(None))
else:
    rutas = especificacion.submodule_search_locations
    ruta = list(rutas)[0] if rutas else especificacion.origin
    nombre = {paquete!r}.split(".")[0]
    distribuciones = importlib.metadata.packages_distributions().get(nombre) or []
    version = None
    if distribuciones:
        try:
            version = importlib.metadata.version(distribuciones[0])
        except importlib.metadata.PackageNotFoundError:
            version = None
    print(json.dumps({{"ruta": ruta, "distribucion": distribuciones[0] if distribuciones else None,
                      "version": version}}))
"""


def ubicacion_instalada(paquete: str) -> dict | None:
    """Where the interpreter that runs this process would import `paquete` from, and its version.

    This is the route a consumer repository takes: an instrument installed into the environment
    has no sibling clone to point `--raiz` at. Its `commit` is not measurable from the
    installation, so it is reported as absent and a pin, when one is declared, says which
    commit the installation is supposed to be -- as a declaration, never as a measurement.
    """
    try:
        hecho = subprocess.run([sys.executable, "-c", _SONDEO_INSTALADO.format(paquete=paquete)],
                               capture_output=True, text=True, timeout=120,
                               env={k: v for k, v in os.environ.items()
                                    if k in ("PATH", "HOME", "SYSTEMROOT")})
    except (OSError, subprocess.SubprocessError):
        return None
    if hecho.returncode != 0:
        return None
    try:
        datos = json.loads(hecho.stdout or "null")
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict) or not datos.get("ruta"):
        return None
    return datos


def identificar(repo: str, instrumento: Instrumento) -> dict:
    return {
        "version": version_de(repo, instrumento.paquete),
        "commit": commit_de(repo),
        "huella": huella_de(repo, instrumento.paquete),
    }
