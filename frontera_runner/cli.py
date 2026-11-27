"""The whole surface: one subject in, one sealed receipt out -- or two receipts in, one verdict.

Exit codes are the contract and there are four: `0` measured and clean, `1` measured with
findings, `2` something could not be measured (never read as clean), `3` the receipt failed its
own laws. Bad invocation is `20`, kept apart from `2` for the same reason the instruments keep it
apart: a typo says nothing about the subject.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .recibo import comparar, construir, escribir, salida_global, verificar
from .render import markdown, markdown_diff

RC_OK = 0
RC_HALLAZGOS = 1
RC_HUECO = 2
RC_INCONSISTENTE = 3
RC_ARIDAD = 20


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="frontera-runner",
        description="Una corrida de los cuatro instrumentos de frontera, un recibo sellado, "
                    "un check de PR.")
    p.add_argument("sujeto", nargs="?", default=".", help="árbol a medir (por defecto .)")
    p.add_argument("--json", action="store_true",
                   help="escribir el recibo JSON canónico en stdout, no el Markdown")
    p.add_argument("--recibo", metavar="RUTA", help="escribir el recibo JSON en RUTA")
    p.add_argument("--md", metavar="RUTA", help="escribir el Markdown en RUTA")
    p.add_argument("--raiz", metavar="DIR", default=None,
                   help="prometer que los instrumentos son estos clones; sin esta bandera se "
                        "prueba el hermano de este repositorio y después el paquete instalado")
    p.add_argument("--pines", metavar="RUTA", default=None,
                   help="JSON con el commit/versión declarados de cada instrumento")
    p.add_argument("--tiempo-limite", type=int, default=300, metavar="SEGUNDOS",
                   help="presupuesto por instrumento (por defecto 300)")
    p.add_argument("--forzar-todos", action="store_true",
                   help="saltarse el triaje y correr los cuatro: sirve para medir lo que el "
                        "triaje ahorra, no para publicar un check")
    p.add_argument("--self-test", action="store_true",
                   help="comprobar determinismo y sello sobre un sujeto vacío")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _parser_diff() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="frontera-runner diff",
        description="Comparar dos recibos sellados y decidir si el PR introdujo hallazgos.")
    p.add_argument("--base", metavar="RUTA", required=True, help="recibo de base (main)")
    p.add_argument("--head", metavar="RUTA", required=True, help="recibo de head (el PR)")
    p.add_argument("--json", action="store_true", help="escribir la comparación JSON en stdout")
    p.add_argument("--md", metavar="RUTA", help="escribir el Markdown del comentario en RUTA")
    p.add_argument("--estricto-base", action="store_true",
                   help="RC 2 si base no midió un instrumento que head sí (rutas congeladas)")
    return p


def _leer(ruta: str) -> dict | None:
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return datos if isinstance(datos, dict) else None


def _cargar_pines(ruta: str | None) -> dict:
    """The declared identity of each instrument, as a file: `{"instrumentos": {nombre: {...}}}`."""
    if ruta is None:
        return {}
    datos = _leer(ruta)
    if datos is None:
        raise ValueError(f"no se puede leer el archivo de pines: {ruta}")
    declarados = datos.get("instrumentos", datos)
    return declarados if isinstance(declarados, dict) else {}


def _diff(argv: list[str]) -> int:
    args = _parser_diff().parse_args(argv)
    base, head = _leer(args.base), _leer(args.head)
    if base is None or head is None:
        falta = args.base if base is None else args.head
        print(f"frontera-runner diff: no es un recibo JSON legible: {falta}", file=sys.stderr)
        return RC_ARIDAD
    delta = comparar(base, head, estricto=args.estricto_base)
    texto = markdown_diff(delta)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(texto)
    if args.json:
        from .recibo import canonico

        sys.stdout.write(canonico(delta))
    else:
        sys.stdout.write(texto)
    return delta["rc"]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "diff":
        return _diff(argv[1:])

    args = _parser().parse_args(argv)
    if args.self_test:
        from .recibo import _self_check

        return _self_check()
    if args.tiempo_limite <= 0:
        print("frontera-runner: error: --tiempo-limite tiene que ser positivo", file=sys.stderr)
        return RC_ARIDAD
    try:
        pines = _cargar_pines(args.pines)
    except ValueError as fallo:
        print(f"frontera-runner: error: {fallo}", file=sys.stderr)
        return RC_ARIDAD

    recibo = construir(args.sujeto, args.raiz, args.tiempo_limite,
                       forzar=args.forzar_todos, pines=pines)

    if not verificar(recibo):
        print("frontera-runner: el sello del recibo no recompone", file=sys.stderr)
        return RC_INCONSISTENTE

    texto_md = markdown(recibo)
    if args.recibo:
        escribir(recibo, args.recibo)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(texto_md)

    if args.json:
        from .recibo import canonico

        sys.stdout.write(canonico(recibo))
    else:
        sys.stdout.write(texto_md)
    return salida_global(recibo)[0]


if __name__ == "__main__":
    raise SystemExit(main())
