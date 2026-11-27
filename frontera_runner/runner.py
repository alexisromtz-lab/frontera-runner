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

#: How the bytes that ran were found. Both are legitimate; they are not interchangeable, because
#: only a checkout has a repository to read a commit from.
CLON = "CLON"
PAQUETE = "PAQUETE"

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


def entorno_de(repo: str | None, base: Mapping[str, str] | None = None, subruta: str = "") -> dict:
    """The environment one instrument runs in: allowlist, plus its package on `PYTHONPATH`.

    `repo=None` means the instrument is installed in this interpreter's environment: there is no
    checkout to put on the path, and setting one would shadow the installation with whatever
    happens to sit beside this repository on the machine that runs it.
    """
    base = os.environ if base is None else base
    entorno = {k: base[k] for k in ENTORNO_PERMITIDO if k in base}
    entorno.update(ENTORNO_FIJO)
    if repo is not None:
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


def _sin_ejecutar(instrumento: inst.Instrumento, estado: str, razon: str,
                  resolucion: Mapping | None = None) -> dict:
    registro = _registro_base(instrumento)
    registro.update({"estado": estado, "razon": razon, "rc": None, "version": None,
                     "commit": None, "huella": None, "procedencia": None, "pin": None,
                     "salida_sha256": None, "denominador": {}, "hallazgos": None,
                     "hallazgos_declarados": None, "unidad_declarada": instrumento.unidad,
                     "huellas_de_hallazgo": None, "identidades_reconcilian": None})
    if resolucion:
        registro.update({k: resolucion.get(k) for k in
                         ("version", "commit", "huella", "procedencia", "pin")})
    return registro


def resolver(instrumento: inst.Instrumento, raiz: str | None = None,
             pines: Mapping | None = None) -> dict:
    """Find the instrument and identify the bytes that will run.

    Two routes, and the difference between them is a promise. An explicit `--raiz` means "measure
    exactly these checkouts": a missing sibling is then `INSTRUMENTO_AUSENTE`, because silently
    substituting an installed copy would answer about a tree nobody asked about. Without `--raiz`
    the sibling convention is tried first and the installed package second, which is the only
    route a consumer repository has -- it has no four sibling clones to point at.

    A pin is a declaration, never a measurement: an installed package has no repository to read a
    commit from, so the declared commit is published as declared and a mismatch with the version
    that is installed is reported as a mismatch instead of being smoothed over.
    """
    pin = None
    if pines and instrumento.nombre in pines:
        pin = dict(pines[instrumento.nombre])
    if raiz is not None:
        repo = os.path.join(raiz, instrumento.nombre)
        if not os.path.isdir(repo):
            return {"modo": CLON, "repo": None, "razon": "INSTRUMENTO_AUSENTE", "pin": pin}
        return {"modo": CLON, "repo": repo, "procedencia": CLON, "pin": pin,
                **inst.identificar(repo, instrumento)}

    vecino = os.path.join(raiz_por_defecto(), instrumento.nombre)
    if os.path.isdir(vecino):
        return {"modo": CLON, "repo": vecino, "procedencia": CLON, "pin": pin,
                **inst.identificar(vecino, instrumento)}

    ubicacion = inst.ubicacion_instalada(instrumento.modulo.split(".")[0])
    if ubicacion is None:
        return {"modo": PAQUETE, "repo": None, "razon": "INSTRUMENTO_AUSENTE", "pin": pin}
    return {"modo": PAQUETE, "repo": None, "procedencia": PAQUETE, "pin": pin,
            "version": ubicacion.get("version"),
            "commit": None,
            # The located directory *is* the package root, so the digest is taken there: the same
            # bytes installed and checked out under `src/` share relative paths and seal equally.
            "huella": inst.huella_de_arbol(ubicacion["ruta"])}


def _juzgar_pin(instrumento: inst.Instrumento, resolucion: Mapping) -> dict | None:
    """Compare the declaration with what is installed. Absent pin, absent evidence.

    A declared commit cannot be verified against an installation -- that is the whole reason it
    is published as declared -- so only the version is checked, and an unverifiable pin is
    reported as `NO_VERIFICABLE`, which is not the same word as `VERIFICADO`.
    """
    pin = resolucion.get("pin")
    if not pin:
        return None
    declarado = (pin.get("version"), pin.get("commit"))
    medido = (resolucion.get("version"), resolucion.get("commit"))
    veredicto = {"version_declarada": declarado[0], "commit_declarado": declarado[1],
                 "version_medida": medido[0], "commit_medido": medido[1]}
    if declarado[0] and medido[0] and str(declarado[0]) != str(medido[0]):
        veredicto.update({"estado": "DIVERGE", "razon": "LA_VERSION_INSTALADA_NO_ES_LA_DECLARADA"})
    elif declarado[1] and medido[1]:
        vale = _pin_apunta_a(declarado[1], medido[1])
        veredicto.update({"estado": "VERIFICADO" if vale else "DIVERGE",
                          "razon": None if vale else "EL_COMMIT_MEDIDO_NO_ES_EL_DECLARADO"})
    else:
        veredicto.update({"estado": "NO_VERIFICABLE",
                          "razon": "LA_INSTALACION_NO_DECLARA_COMMIT"})
    return veredicto


def _pin_apunta_a(declarado: str, medido: str) -> bool:
    """A declared commit may be abbreviated, exactly as `git rev-parse` reads one.

    Anything shorter than seven characters is not an identifier in this repository, so it is not
    honoured as one here either: a two-character prefix matches everything and proves nothing.
    """
    declarado, medido = str(declarado).strip().lower(), str(medido).strip().lower()
    if len(declarado) < 7:
        return False
    return medido.startswith(declarado)


def ejecutar(instrumento: inst.Instrumento, sujeto: str, raiz: str | None, triaje: Mapping,
             tiempo_limite: int = TIEMPO_LIMITE_POR_DEFECTO,
             base_entorno: Mapping[str, str] | None = None,
             pines: Mapping | None = None) -> dict:
    """One instrument, one subprocess, one record. Never raises on a bad subject."""
    decision = triaje[instrumento.nombre]
    if decision["estado"] == NO_APLICABLE:
        return _sin_ejecutar(instrumento, NO_APLICABLE, decision["razon"])

    resolucion = resolver(instrumento, raiz, pines)
    if resolucion["repo"] is None and resolucion.get("razon"):
        return _sin_ejecutar(instrumento, NO_EJECUTADO, resolucion["razon"], resolucion)
    repo = resolucion["repo"]

    manifiesto = decision["insumos"].get("manifiesto")
    argv = [sys.executable, "-m", *instrumento.comando(manifiesto)]
    registro = _registro_base(instrumento, manifiesto)
    registro.update({k: resolucion.get(k) for k in
                     ("version", "commit", "huella", "procedencia")})
    registro.update({"pin": _juzgar_pin(instrumento, resolucion),
                     "modo_resolucion": resolucion["modo"],
                     "denominador": {}, "hallazgos": None, "hallazgos_declarados": None,
                     "unidad_declarada": instrumento.unidad, "huellas_de_hallazgo": None,
                     "identidades_reconcilian": None, "salida_sha256": None})

    try:
        hecho = subprocess.run(argv, cwd=sujeto,
                               env=entorno_de(repo, base_entorno, instrumento.subruta),
                               capture_output=True, timeout=tiempo_limite)
    except subprocess.TimeoutExpired:
        registro.update({"estado": NO_MEDIDO, "razon": "TIEMPO_AGOTADO", "rc": None})
        return registro
    except (OSError, subprocess.SubprocessError) as fallo:
        registro.update({"estado": NO_MEDIDO, "razon": _limpiar(f"NO_ARRANCO: {fallo}", sujeto,
                                                                raiz or repo),
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
        detalle = _limpiar((hecho.stderr or b"").decode("utf-8", "replace").strip(), sujeto,
                           raiz or repo)
        razon = f"{etiqueta}" if not detalle else f"{etiqueta}: {detalle}"
        registro.update({"estado": NO_MEDIDO, "razon": razon})
        return registro

    try:
        salida = json.loads(crudo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # An instrument that exits on a contract code and prints no JSON has crashed; its last
        # stderr line is the only evidence of why, so it travels with the state.
        cola = [l for l in _limpiar((hecho.stderr or b"").decode("utf-8", "replace"),
                                    sujeto, raiz or repo).splitlines() if l.strip()]
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

    identidades = instrumento.identidades(salida)
    if identidades is None:
        # The count without the names is a number no diff can act on: a gate that reported
        # "two findings became two findings" would pass a pull request that swapped both.
        registro.update({"estado": NO_MEDIDO, "razon": "SALIDA_SIN_IDENTIDADES",
                         "hallazgos_declarados": hallazgos,
                         "denominador": instrumento.denominador(salida)})
        return registro

    # Sorted here, not trusted from the payload: two runs must seal the same bytes even if an
    # instrument walks a filesystem whose iteration order is not stable.
    nombres = sorted(identidades)
    if instrumento.reconciliar is not None:
        reconcilia = bool(instrumento.reconciliar(salida, nombres))
    else:
        reconcilia = len(nombres) == hallazgos
    if not reconcilia:
        registro.update({"estado": NO_MEDIDO, "razon": "IDENTIDADES_NO_RECONCILIAN",
                         "hallazgos_declarados": hallazgos,
                         "denominador": instrumento.denominador(salida),
                         "huellas_de_hallazgo": nombres})
        return registro

    registro.update({
        "estado": APLICABLE,
        "razon": etiqueta,
        "denominador": instrumento.denominador(salida),
        "hallazgos": len(nombres),
        "hallazgos_declarados": hallazgos,
        "huellas_de_hallazgo": nombres,
        "identidades_reconcilian": True,
    })
    return registro


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def correr(sujeto: str, raiz: str | None = None, tiempo_limite: int = TIEMPO_LIMITE_POR_DEFECTO,
           base_entorno: Mapping[str, str] | None = None, forzar: bool = False,
           pines: Mapping | None = None) -> dict:
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
            instrumento, sujeto, raiz, triaje, tiempo_limite, base_entorno, pines)
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


__all__ = ["correr", "ejecutar", "entorno_de", "resolver", "sujeto_git", "raiz_por_defecto",
           "APLICABLE", "NO_APLICABLE", "NO_MEDIDO", "NO_EJECUTADO", "CLON", "PAQUETE"]
