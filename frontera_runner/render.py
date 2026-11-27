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
        lineas.append(f"- procedencia: `{registro.get('procedencia') or 'NO_MEDIDO'}` · "
                      f"commit: `{(registro.get('commit') or 'NO_MEDIDO')[:12]}`")
        if registro.get("pin"):
            pin = registro["pin"]
            lineas.append(f"- pin declarado: `{pin.get('estado')}` · "
                          f"commit `{str(pin.get('commit_declarado') or 'NO_MEDIDO')[:12]}`")
        denominador = _denominador_celda(registro["denominador"])
        lineas.append(f"- denominador: {denominador}")
        if registro.get("hallazgos_declarados") is not None:
            lineas.append(f"- hallazgos declarados por el instrumento: "
                          f"`{registro['hallazgos_declarados']}` en unidades de "
                          f"`{registro.get('unidad_declarada')}`")
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


#: How many identities of one kind a pull-request comment lists. The receipt carries all of them;
#: a comment that pastes ten thousand lines is a comment nobody reads, and GitHub truncates it.
TOPE_IDENTIDADES = 25


def _identidades(titulo: str, claves: list[str]) -> list[str]:
    if not claves:
        return []
    lineas = [f"- {titulo}: {len(claves)}"]
    for clave in claves[:TOPE_IDENTIDADES]:
        lineas.append(f"  - `{clave}`")
    if len(claves) > TOPE_IDENTIDADES:
        lineas.append(f"  - … {len(claves) - TOPE_IDENTIDADES} más en el recibo JSON")
    return lineas


def markdown_diff(delta: Mapping, tope: int = TOPE) -> str:
    """The one comment a pull request gets: what base said, what head says, and the verdict."""
    resumen = delta["resumen"]
    lineas = [
        f"# Frontera · diff base→head · {delta['veredicto']} · RC `{delta.get('rc')}`",
        "",
        f"base `HEAD {(delta['sujeto']['base'] or 'NO_MEDIDO')[:12]}` · "
        f"head `HEAD {(delta['sujeto']['head'] or 'NO_MEDIDO')[:12]}`",
        "",
        f"nuevos `{resumen['nuevos']}` · resueltos `{resumen['resueltos']}` · "
        f"pérdidas de medición `{resumen['perdidas_de_medicion']}` · "
        f"mediciones no hechas `{resumen.get('mediciones_no_hechas', 0)}` · "
        f"instrumentos sin base medida `{resumen['ganancias_de_medicion']}` · "
        f"superficies nuevas `{resumen.get('superficies_nuevas', 0)}` · "
        f"no atribuibles `{resumen['no_atribuibles']}`",
        "",
        "## Instrumentos",
        "",
        "| instrumento | base | head | nuevos | resueltos | lectura |",
        "|---|---|---|---|---|---|",
    ]
    for nombre, fila in sorted(delta["instrumentos"].items()):
        lineas.append(
            f"| `{nombre}` | {fila['estado_base']} | {fila['estado_head']} | "
            f"{len(fila['nuevos'])} | {len(fila['resueltos'])} | "
            f"{fila['nota'] or ('delta atribuible' if fila['atribuible'] else '—')} |")
    lineas.append("")

    detalle = []
    for nombre, fila in sorted(delta["instrumentos"].items()):
        bloque = [f"### `{nombre}`", ""]
        bloque += _identidades("nuevos en head", fila["nuevos"])
        bloque += _identidades("resueltos desde base", fila["resueltos"])
        if fila.get("hallazgos_de_base_perdidos") is not None:
            bloque.append(f"- la medición de base nombraba "
                          f"`{fila['hallazgos_de_base_perdidos']}` hallazgo(s) que head ya no mide: "
                          "una pérdida de medición no es una resolución")
        if fila["nota"] == "MEDICION_NO_HECHA":
            bloque.append("- uno de los dos lados no respondió -- agotamiento, caída o salida "
                          "ilegible: un hueco no es una ausencia, y no es verde")
        if fila["nota"] == "SUPERFICIE_NUEVA":
            bloque.append(f"- base no tenía superficie que medir y head la trae: "
                          f"`{len(fila['nuevos'])}` hallazgo(s) sobre superficie que este cambio "
                          "crea, contados como regresión")
        if fila.get("hallazgos_de_head_sin_base") is not None:
            bloque.append(f"- base no medía este instrumento; head declara "
                          f"`{fila['hallazgos_de_head_sin_base']}` hallazgo(s) sin base contra la "
                          "cual compararlos")
        if bloque[-1] != "":
            detalle += bloque + [""]
    if detalle:
        lineas += ["## Detalle", ""] + detalle

    lineas += ["## Sellos verificados", "",
               f"- base: `{'recompone' if delta['verificacion']['base'] else 'NO RECOMPONE'}` · "
               f"`{delta['sello']['base']}`",
               f"- head: `{'recompone' if delta['verificacion']['head'] else 'NO RECOMPONE'}` · "
               f"`{delta['sello']['head']}`",
               ""]
    return recortar("\n".join(lineas).rstrip("\n") + "\n", tope)


__all__ = ["markdown", "markdown_diff", "recortar", "TOPE", "TOPE_IDENTIDADES"]
