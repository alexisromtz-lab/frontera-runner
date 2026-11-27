"""The whole surface: one subject in, one sealed receipt out.

Exit codes are the contract and there are four: `0` measured and clean, `1` measured with
findings, `2` something could not be measured (never read as clean), `3` the receipt failed its
own laws. Bad invocation is `20`, kept apart from `2` for the same reason the instruments keep it
apart: a typo says nothing about the subject.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .recibo import construir, escribir, salida_global, verificar
from .render import markdown
from .runner import raiz_por_defecto

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
                   help="directorio donde viven los clones de los instrumentos "
                        "(por defecto, el hermano de este repositorio)")
    p.add_argument("--tiempo-limite", type=int, default=300, metavar="SEGUNDOS",
                   help="presupuesto por instrumento (por defecto 300)")
    p.add_argument("--forzar-todos", action="store_true",
                   help="saltarse el triaje y correr los cuatro: sirve para medir lo que el "
                        "triaje ahorra, no para publicar un check")
    p.add_argument("--self-test", action="store_true",
                   help="comprobar determinismo y sello sobre un sujeto vacío")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        from .recibo import _self_check

        return _self_check()
    if args.tiempo_limite <= 0:
        print("frontera-runner: error: --tiempo-limite tiene que ser positivo", file=sys.stderr)
        return RC_ARIDAD

    raiz = args.raiz or raiz_por_defecto()
    recibo = construir(args.sujeto, raiz, args.tiempo_limite, forzar=args.forzar_todos)

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
