"""One receipt: canonical bytes, one seal, and the identities it must carry to be checkable.

A composite report is only worth publishing if a reader can tell which code produced each of its
rows. So every executor travels with its version, the commit of its repository and a digest of
the package that ran, and the whole body is sealed with `sha256` over its own canonical form.
There is no timestamp anywhere: two runs over one tree must produce the same bytes, and a clock
in the receipt would make that false while looking harmless.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter

from . import __version__
from . import instrumentos as inst
from .runner import (APLICABLE, NO_APLICABLE, NO_EJECUTADO, NO_MEDIDO, PAQUETE, correr,
                     sujeto_git)

ESQUEMA = 2
NOMBRE = "frontera-runner"

#: Fields of an executor that say *which bytes* produced its rows. A delta across a change in any
#: of them is not attributable to the pull request, and the comparison says so instead of guessing.
IDENTIDAD_DE_EJECUTOR = ("version", "huella", "procedencia")

#: Every note a delta row can carry, and the four things a note is worth: which counter in the
#: summary it raises, which exit code it earns, where it sits in the published precedence, and
#: the paragraph a human reads in the pull-request comment. This table is the only place those
#: live; nothing downstream may restate any of them.
#:
#: It exists because the pair used to live in three -- the branch that wrote the note, the loop
#: that counted it, and the function that turned the count into an exit code -- and one note was
#: in none: `SIN_MEDICION_EN_NINGUNA_DE_LAS_DOS` was written, read by nobody, and a delta whose
#: only row carried it came out `0 SIN_REGRESION`. Worse, the early return for an unreadable
#: receipt built its summary from a hand-written list that already lagged the real one by a field.
#: A note is a promise that something reads it; `_nota` is where the promise is kept, and `orden`
#: is the published precedence among the codes that tie. A rank may hold two notes only if they
#: publish the same pair -- the tie is them being the same answer under two names, not a race that
#: `sorted` settles by the order the dict literal happens to be written in.
#:
#: `detalle` is the same promise kept for the reader who only sees the comment: it used to be an
#: `if fila["nota"] == ...` in `render.markdown_diff`, so a note added here was counted and gated
#: and still arrived as a bare row with no explanation. `None` means the note needs no paragraph;
#: a row that omits the key has not said which, and `validar_notas` refuses it at import.
#:
#: `rc_estricto` is the same note read by a frozen path: a base that never answered is not a
#: statement about the pull request, and a gate on a frozen route would rather stop than guess.
#: Endurecer es la unica direccion: `rc_estricto >= rc` y nunca `0`, o el flag que existe para
#: quitar verdes estaria firmando uno.
NOTAS = {
    "PERDIDA_DE_MEDICION": {"contador": "perdidas_de_medicion",
                            "veredicto": "PERDIDA_DE_MEDICION", "rc": 2, "orden": 0,
                            "detalle": None},
    "MEDICION_NO_HECHA": {"contador": "mediciones_no_hechas", "veredicto": "MEDICION_NO_HECHA",
                          "rc": 2, "orden": 1,
                          "detalle": "- uno de los dos lados no respondió -- agotamiento, caída "
                                     "o salida ilegible: un hueco no es una ausencia, y no es "
                                     "verde"},
    "IDENTIDAD_DEL_EJECUTOR_DISTINTA": {"contador": "no_atribuibles",
                                        "veredicto": "DELTA_NO_ATRIBUIBLE", "rc": 2, "orden": 2,
                                        "detalle": None},
    "INSTRUMENTO_SOLO_EN_UNA_DE_LAS_DOS": {"contador": "no_atribuibles",
                                           "veredicto": "DELTA_NO_ATRIBUIBLE", "rc": 2, "orden": 2,
                                           "detalle": None},
    "SUPERFICIE_NUEVA": {"contador": "superficies_nuevas", "veredicto": None, "rc": 0, "orden": 3,
                         "detalle": "- base no tenía superficie que medir y head la trae: "
                                    "`{nuevos}` hallazgo(s) sobre superficie que este cambio "
                                    "crea, contados como regresión"},
    "SIN_BASE_MEDIDA": {"contador": "ganancias_de_medicion", "veredicto": None, "rc": 0,
                        "orden": 4, "rc_estricto": 2, "veredicto_estricto": "SIN_BASE_MEDIDA",
                        "detalle": None},
    "SIN_MEDICION_EN_NINGUNA_DE_LAS_DOS": {"contador": None, "veredicto": None, "rc": 0,
                                           "orden": 5, "detalle": None},
}

#: What every row of `NOTAS` must say, and what it may say additionally. A row missing one of the
#: first is a promise nobody finished making; a row carrying anything else is a field no reader
#: will ever look at, which is the same defect seen from the other side.
COLUMNAS_DE_NOTA = ("contador", "veredicto", "rc", "orden", "detalle")
#: What a note publishes to the caller. Two notes at the same `orden` have to agree on all four or
#: the precedence between them is the insertion order of this file and nobody published it.
COLUMNAS_PUBLICADAS = ("rc", "veredicto", "rc_estricto", "veredicto_estricto")
COLUMNAS_OPCIONALES = ("rc_estricto", "veredicto_estricto")


def validar_notas(tabla: dict | None = None) -> dict:
    """Refuse a catalogue row that is not a complete descriptor, at import and not at read time.

    A note is worth exactly four things and it is only a note if all four are declared. The cost of
    checking is one pass over seven rows at import; the cost of not checking is a note that is
    counted and gated but arrives to the reader unexplained -- which is how the previous version of
    this file lost the paragraph for every note whose prose lived in `render`.

    A second pass refuses a tie in `orden` that is not a genuine equality: `salida_global` walks the
    table sorted by rank and returns the first note with a non-zero counter, so two notes sharing a
    rank are spent in the order this file lists them. While both publish the same pair that order is
    invisible; the day one of them gains a distinct `veredicto` or `rc_estricto`, the winner is
    decided by a dict literal and no test would say so.

    And a row may not declare a strict rank that loosens: `--estricto-base` exists so a frozen route
    stops where a normal route would continue, so `rc_estricto` is at least `rc` and never `0`. A
    strict answer of `0` is the identity, and a strict answer below the normal one is the flag
    signing the green it was added to withdraw.
    """
    tabla = NOTAS if tabla is None else tabla
    for nota, lectura_de_la_nota in tabla.items():
        faltan = [columna for columna in COLUMNAS_DE_NOTA if columna not in lectura_de_la_nota]
        sobran = [columna for columna in lectura_de_la_nota
                  if columna not in COLUMNAS_DE_NOTA + COLUMNAS_OPCIONALES]
        sueltas = (("rc_estricto" in lectura_de_la_nota)
                   != ("veredicto_estricto" in lectura_de_la_nota))
        if faltan or sobran or sueltas:
            raise KeyError(f"nota incompleta en NOTAS: {nota!r} "
                           f"(faltan={faltan}, sobran={sobran}, estricto_medio={sueltas})")
        normal = lectura_de_la_nota["rc"]
        estricto = lectura_de_la_nota.get("rc_estricto")
        if estricto is not None and (estricto <= 0 or estricto < normal):
            raise KeyError(f"modo estricto que afloja en NOTAS: {nota!r} publica rc={normal!r} y "
                           f"rc_estricto={estricto!r}; un rango estricto endurece (>= rc) y "
                           f"nunca es 0")
    rangos = {}
    for nota, lectura_de_la_nota in tabla.items():
        rango = lectura_de_la_nota["orden"]
        publica = tuple(lectura_de_la_nota.get(columna) for columna in COLUMNAS_PUBLICADAS)
        previa = rangos.setdefault(rango, (nota, publica))
        if previa[1] != publica:
            raise KeyError(f"empate sin precedencia en NOTAS: {previa[0]!r} y {nota!r} comparten "
                           f"orden={rango!r} y publican distinto: {previa[1]} != {publica}")
    return tabla


def lectura(nota: str) -> dict:
    """The descriptor of one note. The single reader every consumer goes through."""
    try:
        return NOTAS[nota]
    except KeyError:
        raise KeyError(f"nota sin lector en NOTAS: {nota!r}") from None


def _nota(fila: dict, nota: str) -> dict:
    """Write a note onto a row, refusing any note that has no descriptor in the table.

    A note invented without a row in `NOTAS` fails here, in the branch that invented it, instead of
    travelling as a string nobody counts. This is the mechanism; the test that walks the whole
    catalogue is only its witness.
    """
    lectura(nota)
    fila["nota"] = nota
    return fila


validar_notas()


def _resumen_vacio() -> dict:
    """A summary with every counter the table declares, at zero. Never a hand-written list."""
    resumen = {"nuevos": 0, "resueltos": 0}
    for lectura in NOTAS.values():
        if lectura["contador"]:
            resumen[lectura["contador"]] = 0
    return resumen


def canonico(datos) -> str:
    """The one serialisation: sorted keys, no ASCII escaping, one trailing newline."""
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def sha256_de(datos: bytes) -> str:
    return "sha256:" + hashlib.sha256(datos).hexdigest()


def interprete() -> dict:
    """What ran the code. Declared because a digest of the bytes does not name the runtime."""
    return {"implementacion": platform.python_implementation(),
            "version": platform.python_version(),
            "ejecutable": os.path.basename(sys.executable)}


def _generador() -> dict:
    aqui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return {
        "nombre": NOMBRE,
        "version": __version__,
        "commit": inst.commit_de(aqui),
        "huella": inst.huella_de(aqui, "frontera_runner"),
    }


def _triaje_minimo(triaje: dict) -> dict:
    return {nombre: {"estado": t["estado"], "razon": t["razon"], "insumos": t["insumos"]}
            for nombre, t in sorted(triaje.items())}


def _denominador(ejecutores: dict) -> dict:
    cuenta = {APLICABLE: 0, NO_APLICABLE: 0, NO_MEDIDO: 0, NO_EJECUTADO: 0}
    con = sin = 0
    for registro in ejecutores.values():
        cuenta[registro["estado"]] += 1
        if registro["estado"] == APLICABLE:
            if registro["hallazgos"]:
                con += 1
            else:
                sin += 1
    return {
        "instrumentos": len(ejecutores),
        "aplicables": cuenta[APLICABLE],
        "con_hallazgos": con,
        "sin_hallazgos": sin,
        "no_aplicables": cuenta[NO_APLICABLE],
        "no_medidos": cuenta[NO_MEDIDO],
        "no_ejecutados": cuenta[NO_EJECUTADO],
    }


def leyes(cuerpo: dict) -> dict:
    """Identities the receipt must satisfy about itself. A false one is a defect, not a footnote."""
    ejecutores = cuerpo["ejecutores"]
    cuenta = _denominador(ejecutores)
    particion = (cuenta["aplicables"] + cuenta["no_aplicables"] + cuenta["no_medidos"]
                 + cuenta["no_ejecutados"])
    # An installed package has no repository to read a commit from, so the commit cannot be
    # demanded of it: the version, the digest of the bytes and the `procedencia` that says which
    # route was taken are what a reader needs to know which code spoke.
    identificados = all(
        registro["estado"] != APLICABLE
        or (registro["version"] and registro["huella"]
            and (registro["commit"] or registro.get("procedencia") == PAQUETE))
        for registro in ejecutores.values())
    medidos = all(
        registro["estado"] != APLICABLE or registro["hallazgos"] is not None
        for registro in ejecutores.values())
    # The count and the census must be the same number, or the delta downstream compares a
    # quantity with a list and the gate passes a swap for a no-op.
    nombrados = all(
        registro["estado"] != APLICABLE
        or (registro.get("huellas_de_hallazgo") is not None
            and registro["hallazgos"] == len(registro["huellas_de_hallazgo"])
            and registro.get("identidades_reconcilian") is True)
        for registro in ejecutores.values())
    razonados = all(
        registro["estado"] == APLICABLE or bool(registro["razon"])
        for registro in ejecutores.values())
    return {
        "particion": particion == cuenta["instrumentos"],
        "identidad_de_ejecutores": identificados,
        "medido_es_numero": medidos,
        "hallazgos_nombrados": nombrados,
        "estado_sin_medicion_nombra_su_razon": razonados,
        "instrumentos": cuenta["instrumentos"],
        "suma_estados": particion,
    }


def construir(sujeto: str, raiz: str | None = None, tiempo_limite: int = 300,
              base_entorno=None, forzar: bool = False, pines=None) -> dict:
    """Measure the subject and return the sealed receipt. No wall clock, no paths.

    `raiz=None` is not "the default directory": it is the absence of a promise about where the
    instruments live, which lets the resolver try the sibling convention and then the installed
    package. Passing `--raiz` promises checkouts, and a missing one is then a hole, not a
    substitution.
    """
    cuerpo = correr(sujeto, raiz, tiempo_limite, base_entorno, forzar, pines)
    recibo = {
        "schema": ESQUEMA,
        "generador": _generador(),
        "interprete": interprete(),
        "sujeto": {**sujeto_git(sujeto),
                   "superficie": {k: v for k, v in cuerpo["superficie"].items()}},
        "modo": cuerpo["modo"],
        "triaje": _triaje_minimo(cuerpo["triaje"]),
        "ejecutores": {n: e for n, e in sorted(cuerpo["ejecutores"].items())},
        "denominador": _denominador(cuerpo["ejecutores"]),
    }
    recibo["leyes"] = leyes(recibo)
    recibo["sello"] = sha256_de(canonico(recibo).encode("utf-8"))
    return recibo


def verificar(recibo: dict) -> bool:
    """Recompute the seal over everything but the seal itself."""
    sin_sello = {k: v for k, v in recibo.items() if k != "sello"}
    return recibo.get("sello") == sha256_de(canonico(sin_sello).encode("utf-8"))


def salida_global(recibo: dict) -> tuple[int, str]:
    """The composite exit code and its one-word reason.

    Precedence is declared: a body whose seal or whose laws do not close is `3`, never a verdict,
    because then nothing below it is worth reading. Then a subject with nothing measurable is `2`,
    a finding is `1` because it is actionable, and anything unmeasured keeps the run at `2`.
    """
    if not verificar(recibo):
        return 3, "RECIBO_INCONSISTENTE"
    if not all(v for k, v in recibo["leyes"].items() if isinstance(v, bool)):
        return 3, "RECIBO_INCONSISTENTE"
    denominador = recibo["denominador"]
    if denominador["aplicables"] == 0 and denominador["no_medidos"] == 0:
        return 2, "SIN_SUPERFICIE"
    if denominador["con_hallazgos"]:
        return 1, "CON_HALLAZGOS"
    if denominador["no_medidos"] or denominador["no_ejecutados"]:
        return 2, "HUECO_DE_MEDICION"
    return 0, "SIN_HALLAZGOS"


def escribir(recibo: dict, ruta: str) -> str:
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(canonico(recibo))
    return ruta


def _delta_de_ejecutor(nombre: str, antes: dict, despues: dict) -> dict:
    """Classify one instrument's move from base to head. Every branch is a named verdict.

    The trap this function exists to close is the unmeasured green: if a pull request deletes the
    anchor manifest, the guard stops measuring and its zero findings would read as "nothing left
    to fix". A measurement that disappears is a loss, and a loss never counts as a resolution.
    """
    fila = {"estado_base": antes["estado"], "estado_head": despues["estado"],
            "nuevos": [], "resueltos": [], "atribuible": True, "nota": None}
    identidades = [(antes.get(k), despues.get(k)) for k in IDENTIDAD_DE_EJECUTOR]
    # An identity can only be *different* from another one. When the instrument never ran on one
    # side -- `NO_APLICABLE` publishes no version -- there is nothing to reconcile, and calling
    # that "a different executor" would withdraw attribution from a change that simply turned the
    # instrument on. Divergence needs two identities to diverge.
    if all(a is not None and b is not None for a, b in identidades) \
            and any(a != b for a, b in identidades):
        fila["atribuible"] = False
        _nota(fila, "IDENTIDAD_DEL_EJECUTOR_DISTINTA")

    if antes["estado"] == APLICABLE and despues["estado"] == APLICABLE:
        cuenta_antes = Counter(antes.get("huellas_de_hallazgo") or [])
        cuenta_despues = Counter(despues.get("huellas_de_hallazgo") or [])
        fila["nuevos"] = sorted((cuenta_despues - cuenta_antes).elements())
        fila["resueltos"] = sorted((cuenta_antes - cuenta_despues).elements())
        return fila

    if antes["estado"] == APLICABLE:
        fila["atribuible"] = False
        _nota(fila, "PERDIDA_DE_MEDICION")
        fila["hallazgos_de_base_perdidos"] = antes.get("hallazgos")
        return fila

    if despues["estado"] == APLICABLE:
        if antes["estado"] == NO_APLICABLE and fila["atribuible"]:
            # The pull request created the surface, so what fails on it is the pull request's.
            # Base was not blind here: it answered "nothing of mine to measure", which is a
            # measurement of absence, not a hole. A hole is `NO_MEDIDO`, and only that is
            # `SIN_BASE_MEDIDA` -- otherwise adding the first TypeScript file next to a
            # diverging Python port would read as green.
            _nota(fila, "SUPERFICIE_NUEVA")
            fila["nuevos"] = sorted(despues.get("huellas_de_hallazgo") or [])
            return fila
        _nota(fila, "SIN_BASE_MEDIDA")
        fila["hallazgos_de_head_sin_base"] = despues.get("hallazgos")
        return fila

    if NO_MEDIDO in (antes["estado"], despues["estado"]):
        # A hole is not an absence, and only one of the two is green. `NO_APLICABLE` on both
        # sides is a measurement of absence: the instrument looked and there was nothing of its
        # universe. `NO_MEDIDO` is the instrument being pointed at the subject and not answering
        # -- a timeout, a crash, a garbage line. Both used to land on the same note, so a run
        # that timed out on head read exactly like a tree with nothing to measure: green.
        fila["atribuible"] = False
        _nota(fila, "MEDICION_NO_HECHA")
        return fila
    _nota(fila, "SIN_MEDICION_EN_NINGUNA_DE_LAS_DOS")
    return fila


def comparar(base: dict, head: dict, estricto: bool = False) -> dict:
    """The differential gate: verify both seals first, then say what the pull request changed.

    The seal is recomputed before a single field is read. A comparison over a receipt whose body
    does not match its own digest is a comparison over a document somebody edited, and it does
    not matter what it says. Both receipts must also be the same schema: a v1 receipt has no
    census and cannot be differenced, and pretending otherwise would report every finding of the
    newer side as new.

    `estricto` reads the same delta with a gate's eyes: a base that never answered stops being a
    note about provenance and becomes RC 2. It is off by default because a pull request that adds
    a surface where base had nothing to measure is normally the pull request's own business.
    """
    verificacion = {"base": verificar(base), "head": verificar(head)}
    esquema = {"base": base.get("schema"), "head": head.get("schema")}
    leyes_ok = {}
    for lado, cuerpo in (("base", base), ("head", head)):
        valores = cuerpo.get("leyes") or {}
        leyes_ok[lado] = bool(valores) and all(v for v in valores.values() if isinstance(v, bool))

    delta = {
        "verificacion": verificacion,
        "schema": esquema,
        "leyes": leyes_ok,
        "sujeto": {"base": (base.get("sujeto") or {}).get("head"),
                   "head": (head.get("sujeto") or {}).get("head")},
        "sello": {"base": base.get("sello"), "head": head.get("sello")},
        "instrumentos": {},
        "resumen": {},
    }
    if not all(verificacion.values()) or not all(leyes_ok.values()) \
            or esquema["base"] != esquema["head"] or esquema["base"] != ESQUEMA:
        delta["resumen"] = _resumen_vacio()
        delta["rc"], delta["veredicto"] = salida_de_comparacion(delta, estricto)
        return delta

    ejecutores_base = base.get("ejecutores") or {}
    ejecutores_head = head.get("ejecutores") or {}
    for nombre in sorted(set(ejecutores_base) | set(ejecutores_head)):
        if nombre not in ejecutores_base or nombre not in ejecutores_head:
            delta["instrumentos"][nombre] = _nota({
                "estado_base": (ejecutores_base.get(nombre) or {}).get("estado"),
                "estado_head": (ejecutores_head.get(nombre) or {}).get("estado"),
                "nuevos": [], "resueltos": [], "atribuible": False, "nota": None},
                "INSTRUMENTO_SOLO_EN_UNA_DE_LAS_DOS")
            continue
        delta["instrumentos"][nombre] = _delta_de_ejecutor(
            nombre, ejecutores_base[nombre], ejecutores_head[nombre])

    filas = delta["instrumentos"].values()
    resumen = _resumen_vacio()
    resumen["nuevos"] = sum(len(f["nuevos"]) for f in filas if f["atribuible"])
    resumen["resueltos"] = sum(len(f["resueltos"]) for f in filas if f["atribuible"])
    # One pass, one table: a note raises exactly the counter the table names, and a counter that
    # is not in the table cannot be raised. `Counter` because two notes may share a counter --
    # an identity divergence and an instrument present on one side only are both "no atribuible".
    for nota, cuantas in Counter(f["nota"] for f in filas if f["nota"]).items():
        contador = NOTAS[nota]["contador"]
        if contador:
            resumen[contador] += cuantas
    delta["resumen"] = resumen
    delta["rc"], delta["veredicto"] = salida_de_comparacion(delta, estricto)
    return delta


def salida_de_comparacion(delta: dict, estricto: bool = False) -> tuple[int, str]:
    """The comparison's exit code, with the same precedence discipline as the single receipt.

    `3` before anything: an unreadable receipt is not a verdict. Then the notes, in the published
    order they carry in `NOTAS` -- a measurement that disappeared, an instrument that never
    answered, a delta produced by different bytes than the ones in base. Only then `1`, a finding
    that was not in base, and `0`. A patch that merely bumps an instrument is therefore never
    silently green.

    The precedence is not restated here: it is read off the table, so a note added there with an
    exit code is gated without anyone remembering to add a branch.
    """
    if delta.get("verificacion") and not all(delta["verificacion"].values()):
        return 3, "SELLO_NO_RECOMPONE"
    if delta.get("leyes") and not all(delta["leyes"].values()):
        return 3, "LEYES_NO_CIERRAN"
    if delta.get("schema") and delta["schema"]["base"] != delta["schema"]["head"]:
        return 3, "ESQUEMAS_DISTINTOS"
    if delta.get("schema") and ESQUEMA not in (delta["schema"]["base"], delta["schema"]["head"]):
        return 3, "RECIBO_NO_COMPARABLE"
    resumen = delta.get("resumen") or {}
    for lectura in sorted(NOTAS.values(), key=lambda lectura: lectura["orden"]):
        contador = lectura["contador"]
        if not contador or not resumen.get(contador):
            continue
        if estricto and "rc_estricto" in lectura:
            return lectura["rc_estricto"], lectura["veredicto_estricto"]
        if lectura["rc"]:
            return lectura["rc"], lectura["veredicto"]
    if resumen.get("nuevos"):
        return 1, "REGRESION"
    return 0, "SIN_REGRESION"


__all__ = ["construir", "verificar", "salida_global", "canonico", "escribir", "leyes",
           "comparar", "salida_de_comparacion", "ESQUEMA", "NOTAS", "COLUMNAS_DE_NOTA",
           "lectura", "validar_notas", "COLUMNAS_PUBLICADAS"]


def _self_check() -> int:  # pragma: no cover - exercised by the CLI flag, asserted by tests
    """Smallest possible receipt: an empty temporary subject, built twice, compared byte by byte.

    The tools directory is passed explicitly and does not exist, so four instruments are absent by
    construction: this check must measure *this* runner, not whichever instrument checkouts happen
    to sit beside it on the machine that runs it.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as caja:
        ausente = os.path.join(caja, "sin-herramientas")
        primero = construir(caja, ausente)
        segundo = construir(caja, ausente)
        iguales = canonico(primero) == canonico(segundo)
        sello_ok = verificar(primero)
        roto = dict(primero)
        roto["denominador"] = dict(primero["denominador"], aplicables=99)
        sello_roto = not verificar(roto)
        delta = comparar(primero, segundo)
        delta_ok = delta["rc"] == 0 and delta["resumen"]["nuevos"] == 0
        manipulado = json.loads(canonico(segundo))
        manipulado["sujeto"] = dict(manipulado["sujeto"], head="0" * 40)
        delta_roto = comparar(primero, manipulado)["rc"]
    print(f"destino vacío: {primero['denominador']['instrumentos']} instrumentos, "
          f"{primero['denominador']['no_aplicables']} no aplicables")
    print(f"dos corridas byte-idénticas: {iguales}")
    print(f"sello recompone: {sello_ok} · cuerpo alterado no recompone: {sello_roto}")
    print(f"comparación de un recibo consigo mismo: RC {delta['rc']} · "
          f"recibo manipulado: RC {delta_roto}")
    return 0 if (iguales and sello_ok and sello_roto and delta_ok and delta_roto == 3) else 1
