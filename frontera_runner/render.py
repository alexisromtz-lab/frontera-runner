"""The Markdown a pull request shows: bounded, and honest about the cut.

GitHub refuses a check output over 65 536 characters, and a render that silently drops the tail
is worse than a short one: the reader sees a complete-looking table over a truncated population.
So the render budgets itself, keeps the summary table first, and when it has to cut, it says how
many characters it cut and points at the JSON receipt that carries all of them.
"""

from __future__ import annotations

from typing import Mapping

from .runner import APLICABLE, NO_APLICABLE, NO_EJECUTADO, NO_MEDIDO
from .recibo import salida_global

#: The hard limit GitHub applies to a check output / check run text.
TOPE = 65_536

ESTADO_LEGIBLE = {
    APLICABLE: "APLICABLE",
    NO_APLICABLE: "NO_APLICABLE",
    NO_MEDIDO: "NO_MEDIDO",
    NO_EJECUTADO: "NO_EJECUTADO",
}


def _celda(valor) -> str:
    if valor is None:
        return "`NO_MEDIDO`"
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, (list, tuple)):
        return ", ".join(str(v) for v in valor) if valor else "—"
    return str(valor)


def _denominador_celda(denominador: Mapping) -> str:
    if not denominador:
        return "—"
    return " · ".join(f"{k}={_celda(v)}" for k, v in sorted(denominador.items()))


def _n(cantidad: int, singular: str, plural: str) -> str:
    return f"{cantidad} {singular if cantidad == 1 else plural}"


def _cabecera(recibo: Mapping, rc: int, motivo: str) -> list[str]:
    generador = recibo["generador"]
    denominador = recibo["denominador"]
    sujeto = recibo["sujeto"]
    return [
        f"# Frontera · {_n(denominador['instrumentos'], 'instrumento', 'instrumentos')} · "
        f"{_n(denominador['aplicables'], 'aplicable', 'aplicables')} · {motivo}",
        "",
        f"`{generador['nombre']} {generador['version']}` · "
        f"`commit {generador['commit'] or 'NO_MEDIDO'}` · "
        f"`sello {recibo['sello']}` · RC `{rc}`",
        "",
        f"Modo: `{recibo.get('modo', 'NO_MEDIDO')}` · "
        f"Sujeto: `HEAD {sujeto.get('head') or 'NO_MEDIDO'}` · "
        f"archivos leídos `{sujeto['superficie']['archivos']}` · "
        f"python `{sujeto['superficie']['python']}` · "
        f"pruebas `{sujeto['superficie']['pruebas']}` · "
        f"typescript `{sujeto['superficie']['typescript']}`",
        "",
    ]


def _tabla(recibo: Mapping) -> list[str]:
    filas = ["| instrumento | estado | razón | rc | hallazgos | denominador | versión | commit |",
             "|---|---|---|---|---|---|---|---|"]
    for nombre, registro in sorted(recibo["ejecutores"].items()):
        filas.append(
            f"| `{nombre}` | {ESTADO_LEGIBLE.get(registro['estado'], registro['estado'])} | "
            f"{registro['razon'] or '—'} | "
            f"{_celda(registro['rc'])} | {_celda(registro['hallazgos'])} | "
            f"{_denominador_celda(registro['denominador'])} | "
            f"{_celda(registro['version'])} | `{(registro['commit'] or 'NO_MEDIDO')[:12]}` |")
    filas.append("")
    return filas


def _detalle(recibo: Mapping) -> list[str]:
    lineas = ["## Detalle", ""]
    for nombre, registro in sorted(recibo["ejecutores"].items()):
        estado = ESTADO_LEGIBLE.get(registro["estado"], registro["estado"])
        lineas.append(f"### `{nombre}` — {estado}")
        lineas.append("")
        lineas.append(f"- comando: `{' '.join(registro['comando'])}`")
        lineas.append(f"- razón: {registro['razon'] or '—'}")
        lineas.append(f"- huella del ejecutor: `{registro['huella'] or 'NO_MEDIDO'}`")
        lineas.append(f"- salida sellada: `{registro['salida_sha256'] or 'NO_MEDIDO'}`")
        denominador = _denominador_celda(registro["denominador"])
        lineas.append(f"- denominador: {denominador}")
        lineas.append("")
    return lineas


def _leyes(recibo: Mapping) -> list[str]:
    lineas = ["## Leyes del recibo", ""]
    for nombre, valor in sorted(recibo["leyes"].items()):
        if isinstance(valor, bool):
            lineas.append(f"- `{nombre}`: {'cierra' if valor else 'NO CIERRA'}")
    lineas.append("")
    return lineas


def recortar(texto: str, tope: int = TOPE) -> str:
    """Cut at a line boundary and declare the cut. Never return a silently shorter body."""
    if len(texto) <= tope:
        return texto
    marca = "\n<!-- RECORTADO: {n} carácter(es) omitidos; el recibo JSON lleva el detalle completo -->\n"
    margen = len(marca.format(n=len(texto)))
    corte = texto[: max(0, tope - margen)]
    corte = corte[: corte.rfind("\n") + 1] if "\n" in corte else corte
    return corte + marca.format(n=len(texto) - len(corte))


def markdown(recibo: Mapping, tope: int = TOPE) -> str:
    rc, motivo = salida_global(recibo)
    lineas = _cabecera(recibo, rc, motivo) + _tabla(recibo) + _leyes(recibo) + _detalle(recibo)
    return recortar("\n".join(lineas).rstrip("\n") + "\n", tope)


__all__ = ["markdown", "recortar", "TOPE"]
