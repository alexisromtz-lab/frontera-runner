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

from . import __version__
from . import instrumentos as inst
from .runner import (APLICABLE, NO_APLICABLE, NO_EJECUTADO, NO_MEDIDO, correr, raiz_por_defecto,
                     sujeto_git)

ESQUEMA = 1
NOMBRE = "frontera-runner"


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
    identificados = all(
        registro["estado"] != APLICABLE
        or (registro["version"] and registro["commit"] and registro["huella"])
        for registro in ejecutores.values())
    medidos = all(
        registro["estado"] != APLICABLE or registro["hallazgos"] is not None
        for registro in ejecutores.values())
    razonados = all(
        registro["estado"] == APLICABLE or bool(registro["razon"])
        for registro in ejecutores.values())
    return {
        "particion": particion == cuenta["instrumentos"],
        "identidad_de_ejecutores": identificados,
        "medido_es_numero": medidos,
        "estado_sin_medicion_nombra_su_razon": razonados,
        "instrumentos": cuenta["instrumentos"],
        "suma_estados": particion,
    }


def construir(sujeto: str, raiz: str | None = None, tiempo_limite: int = 300,
              base_entorno=None, forzar: bool = False) -> dict:
    """Measure the subject and return the sealed receipt. No wall clock, no paths."""
    raiz = raiz_por_defecto() if raiz is None else raiz
    cuerpo = correr(sujeto, raiz, tiempo_limite, base_entorno, forzar)
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


__all__ = ["construir", "verificar", "salida_global", "canonico", "escribir", "leyes", "ESQUEMA"]


def _self_check() -> int:  # pragma: no cover - exercised by the CLI flag, asserted by tests
    """Smallest possible receipt: an empty temporary subject, built twice, compared byte by byte."""
    import tempfile

    with tempfile.TemporaryDirectory() as caja:
        primero = construir(caja)
        segundo = construir(caja)
        iguales = canonico(primero) == canonico(segundo)
        sello_ok = verificar(primero)
        roto = dict(primero)
        roto["denominador"] = dict(primero["denominador"], aplicables=99)
        sello_roto = not verificar(roto)
    print(f"destino vacío: {primero['denominador']['instrumentos']} instrumentos, "
          f"{primero['denominador']['no_aplicables']} no aplicables")
    print(f"dos corridas byte-idénticas: {iguales}")
    print(f"sello recompone: {sello_ok} · cuerpo alterado no recompone: {sello_roto}")
    return 0 if (iguales and sello_ok and sello_roto) else 1
