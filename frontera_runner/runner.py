"""Run the instruments the triage admitted, and read them without flattering them.

Every call is a subprocess with the subject as its working directory. Nothing is imported: an
instrument that mutates module state, caches a parse or keeps a global baseline cannot reach
this process, and the isolation works in both directions -- this runner never edits the
instrument's repository, and never reads its internals.

The environment is an allowlist, not an inheritance. A runner that forwards whatever the CI
machine happened to export produces a receipt that cannot be reproduced anywhere else.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import Mapping

from . import instrumentos as inst
from .triaje_frontera import superficie, triar

#: Terminal states of one instrument in one run. There is no "skipped without saying so".
APLICABLE = "APLICABLE"
NO_APLICABLE = "NO_APLICABLE"
NO_MEDIDO = "NO_MEDIDO"
NO_EJECUTADO = "NO_EJECUTADO"

#: Variables the instruments may read. Everything else is dropped, so two machines that export
#: different things still produce the same receipt.
ENTORNO_PERMITIDO = ("PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SYSTEMROOT")
ENTORNO_FIJO = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONIOENCODING": "utf-8",
}

TIEMPO_LIMITE_POR_DEFECTO = 300
_RECORTE_MENSAJE = 400


def entorno_de(repo: str, base: Mapping[str, str] | None = None, subruta: str = "") -> dict:
    """The environment one instrument runs in: allowlist, plus its package on `PYTHONPATH`."""
    base = os.environ if base is None else base
    entorno = {k: base[k] for k in ENTORNO_PERMITIDO if k in base}
    entorno.update(ENTORNO_FIJO)
    entorno["PYTHONPATH"] = os.path.join(repo, subruta) if subruta else repo
    return entorno


def _limpiar(texto: str, sujeto: str, raiz: str) -> str:
    """Keep absolute paths out of the receipt: they name a machine, not a subject."""
    for ruta, token in ((os.path.abspath(sujeto), "<sujeto>"), (os.path.abspath(raiz), "<herramientas>")):
        texto = texto.replace(ruta, token).replace(os.path.realpath(ruta), token)
    return texto[:_RECORTE_MENSAJE]


def _registro_base(instrumento: inst.Instrumento, manifiesto: str | None = None) -> dict:
    return {
        "comando": [instrumento.modulo, *[a.format(manifiesto=manifiesto or "")
                                          for a in instrumento.argumentos]],
        "rc_contrato": {str(c): {"clase": v[0], "etiqueta": v[1]}
                        for c, v in sorted(instrumento.rc_contrato.items())},
    }


def _sin_ejecutar(instrumento: inst.Instrumento, estado: str, razon: str) -> dict:
    registro = _registro_base(instrumento)
    registro.update({"estado": estado, "razon": razon, "rc": None, "version": None,
                     "commit": None, "huella": None, "salida_sha256": None,
                     "denominador": {}, "hallazgos": None})
    return registro


def ejecutar(instrumento: inst.Instrumento, sujeto: str, raiz: str, triaje: Mapping,
             tiempo_limite: int = TIEMPO_LIMITE_POR_DEFECTO,
             base_entorno: Mapping[str, str] | None = None) -> dict:
    """One instrument, one subprocess, one record. Never raises on a bad subject."""
    decision = triaje[instrumento.nombre]
    if decision["estado"] == NO_APLICABLE:
        return _sin_ejecutar(instrumento, NO_APLICABLE, decision["razon"])

    repo = os.path.join(raiz, instrumento.nombre)
    if not os.path.isdir(repo):
        return _sin_ejecutar(instrumento, NO_EJECUTADO, "INSTRUMENTO_AUSENTE")

    manifiesto = decision["insumos"].get("manifiesto")
    argv = [sys.executable, "-m", *instrumento.comando(manifiesto)]
    registro = _registro_base(instrumento, manifiesto)
    registro.update(inst.identificar(repo, instrumento))
    registro.update({"denominador": {}, "hallazgos": None, "salida_sha256": None})

    try:
        hecho = subprocess.run(argv, cwd=sujeto,
                               env=entorno_de(repo, base_entorno, instrumento.subruta),
                               capture_output=True, timeout=tiempo_limite)
    except subprocess.TimeoutExpired:
        registro.update({"estado": NO_MEDIDO, "razon": "TIEMPO_AGOTADO", "rc": None})
        return registro
    except (OSError, subprocess.SubprocessError) as fallo:
        registro.update({"estado": NO_MEDIDO, "razon": _limpiar(f"NO_ARRANCO: {fallo}", sujeto, raiz),
                         "rc": None})
        return registro

    crudo = hecho.stdout or b""
    registro["salida_sha256"] = "sha256:" + _sha256(crudo)

    clase, etiqueta = instrumento.rc_contrato.get(hecho.returncode, (NO_MEDIDO, "RC_NO_DECLARADO"))
    registro["rc"] = hecho.returncode
    if clase == inst.SIN_SUJETO:
        registro.update({"estado": NO_APLICABLE, "razon": f"EL_INSTRUMENTO_NO_VIO_SUJETO: {etiqueta}"})
        return registro
    if clase == NO_MEDIDO:
        detalle = _limpiar((hecho.stderr or b"").decode("utf-8", "replace").strip(), sujeto, raiz)
        razon = f"{etiqueta}" if not detalle else f"{etiqueta}: {detalle}"
        registro.update({"estado": NO_MEDIDO, "razon": razon})
        return registro

    try:
        salida = json.loads(crudo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # An instrument that exits on a contract code and prints no JSON has crashed; its last
        # stderr line is the only evidence of why, so it travels with the state.
        cola = [l for l in _limpiar((hecho.stderr or b"").decode("utf-8", "replace"),
                                    sujeto, raiz).splitlines() if l.strip()]
        razon = "SALIDA_NO_JSON" + (f": {cola[-1][:200]}" if cola else "")
        registro.update({"estado": NO_MEDIDO, "razon": razon})
        return registro
    if not isinstance(salida, dict):
        registro.update({"estado": NO_MEDIDO, "razon": "SALIDA_NO_ES_OBJETO"})
        return registro

    hallazgos = instrumento.hallazgos(salida)
    if hallazgos is None:
        # A "measured" exit code over a payload without the counters is not a zero: the
        # instrument did not say how many, and the receipt must not say it for it.
        registro.update({"estado": NO_MEDIDO, "razon": "SALIDA_SIN_HALLAZGOS_DECLARADOS",
                         "denominador": instrumento.denominador(salida)})
        return registro
    registro.update({
        "estado": APLICABLE,
        "razon": etiqueta,
        "denominador": instrumento.denominador(salida),
        "hallazgos": hallazgos,
    })
    return registro


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def correr(sujeto: str, raiz: str, tiempo_limite: int = TIEMPO_LIMITE_POR_DEFECTO,
           base_entorno: Mapping[str, str] | None = None, forzar: bool = False) -> dict:
    """Triage, run what the triage admitted, and return the measured body of the receipt.

    `forzar` runs every instrument regardless of the gate. It exists to measure what the gate
    saves: without it, "the triage makes runs shorter" would be a claim with no instrument.
    """
    sup = superficie(sujeto)
    triaje = triar(sujeto, sup)
    if forzar:
        triaje = {nombre: {"estado": APLICABLE, "razon": "TRIAJE_FORZADO", "insumos": t["insumos"]}
                  for nombre, t in triaje.items()}
    ejecutores = {}
    for instrumento in inst.INSTRUMENTOS:
        ejecutores[instrumento.nombre] = ejecutar(
            instrumento, sujeto, raiz, triaje, tiempo_limite, base_entorno)
    return {"superficie": sup, "triaje": triaje, "ejecutores": ejecutores,
            "modo": "FORZADO" if forzar else "TRIADO"}


def sujeto_git(sujeto: str) -> dict:
    """The subject's identity: `HEAD`, without the path that names this machine."""
    try:
        hecho = subprocess.run(["git", "-C", sujeto, "rev-parse", "HEAD"],
                               capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {"head": None}
    head = hecho.stdout.strip() if hecho.returncode == 0 else None
    return {"head": head or None}


def raiz_por_defecto() -> str:
    """Sibling-clone convention: the instruments live beside this repository, not inside it."""
    # __file__ is <parent>/frontera_runner/runner.py, so the parent is three levels up.
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


__all__ = ["correr", "ejecutar", "entorno_de", "sujeto_git", "raiz_por_defecto",
           "APLICABLE", "NO_APLICABLE", "NO_MEDIDO", "NO_EJECUTADO"]
