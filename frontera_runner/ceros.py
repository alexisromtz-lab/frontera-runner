"""Dónde un árbol escribe un cero que nadie midió, y sobre qué superficie lo afirma.

Una ausencia se publica como `None` y viaja como `NO_MEDIDO`. Un cero escrito a mano —`.get(k, 0)`
o un `k or 0`— inventa la lectura: el campo existe, cuenta cero, y todo consumidor aguas abajo lo
lee como libro limpio.

El censo es una proyección del árbol de sintaxis sobre las posiciones donde ese cero aparece. Una
proyección sin dominio declarado no mide: devuelve `0` tanto cuando no hay ceros como cuando no
miró, y las dos cosas se leen igual. Por eso el censo publica su denominador —`archivos`,
`podados`, `ilegibles`— en el mismo objeto que sus hallazgos, y un `0` sólo vale junto a él.

El objeto tampoco lleva rutas absolutas: dos clones del mismo árbol, en distinta ruta y distinta
profundidad, tienen que censar byte a byte lo mismo. Dónde vive un árbol es propiedad del
observador; qué escribe, del árbol.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import sys

from .cli import RC_ARIDAD, RC_HALLAZGOS, RC_HUECO, RC_OK
from .recibo import canonico

#: Directorios que el censo no atraviesa, por nombre y por patrón. La lista se declara aquí y su
#: efecto se publica en `podados`: una exclusión declarada vence al default, y una que deja de
#: casar se ve encoger `podados` en vez de desaparecer en silencio.
EXCLUIDOS = (".git", ".hg", ".svn", ".venv*", "venv", "node_modules", "*.egg-info", "build",
             "dist", "__pycache__", ".mypy_cache", ".pytest_cache", ".tox", ".worktrees",
             "site-packages")


def es_cero(valor) -> bool:
    """Un cero es un `int` o un `float` de valor cero. `False` no es un número aquí."""
    return type(valor) in (int, float) and valor == 0


def _podado(nombre: str, patrones) -> bool:
    return any(fnmatch.fnmatchcase(nombre, patron) for patron in patrones)


def _conjunto(texto: str) -> frozenset:
    return frozenset(t for t in (x.strip() for x in texto.split(",")) if t)


def _ceros_de(arbol, relativo: str, permitidos) -> list:
    """`permitidos` nombra lo declarado: la clave de un `get`, o la expresión exacta.

    Una clave nombra una clase —todos los `get('nuevos', 0)` del árbol—; una expresión nombra una
    línea. La expresión es la forma estrecha que hace falta cuando no hay clave que nombrar, como
    en `total = suma or 0`: se declara esa línea, y renombrar la variable la vuelve a delatar.
    """
    hallazgos = []
    for nodo in ast.walk(arbol):
        lectura = (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                   and nodo.func.attr == "get" and len(nodo.args) >= 2
                   and isinstance(nodo.args[1], ast.Constant)
                   and es_cero(nodo.args[1].value))
        caida = (isinstance(nodo, ast.BoolOp) and isinstance(nodo.op, ast.Or)
                 and any(isinstance(v, ast.Constant) and es_cero(v.value) for v in nodo.values))
        if not (lectura or caida):
            continue
        expresion = ast.unparse(nodo)
        clave = None
        if lectura:
            argumento = nodo.args[0]
            clave = argumento.value if isinstance(argumento, ast.Constant) \
                and isinstance(argumento.value, str) else None
        if clave is not None and clave in permitidos:
            continue
        if expresion in permitidos:
            continue
        hallazgos.append({"archivo": relativo, "linea": nodo.lineno,
                          "clave": clave, "expresion": expresion})
    return hallazgos


def censar(raiz, permitidos=frozenset(), excluidos=EXCLUIDOS) -> dict:
    """El censo de un árbol: sus hallazgos y el dominio exacto sobre el que valen.

    `permitidos` son nombres cuyo cero está declarado y no se cuenta: la clave de un `get` o la
    expresión exacta de la línea. Un `get` cuya clave no es una cadena literal publica
    `clave: null` y no se puede desactivar por clave: no hay nombre que declarar, así que tampoco
    hay clase que excusar — sólo la línea, si alguien la escribe entera.
    """
    raiz = os.path.abspath(raiz)
    archivos = 0
    podados = []
    ilegibles = []
    hallazgos = []
    for actual, dirs, ficheros in os.walk(raiz):
        conservados = []
        for nombre in sorted(dirs):
            if _podado(nombre, excluidos):
                podados.append(os.path.relpath(os.path.join(actual, nombre), raiz))
            else:
                conservados.append(nombre)
        dirs[:] = conservados
        for fichero in sorted(ficheros):
            if not fichero.endswith(".py"):
                continue
            ruta = os.path.join(actual, fichero)
            relativo = os.path.relpath(ruta, raiz)
            try:
                with open(ruta, encoding="utf-8") as f:
                    arbol = ast.parse(f.read(), filename=relativo)
            except SyntaxError:
                ilegibles.append({"archivo": relativo, "error": "SINTAXIS"})
                continue
            except OSError:
                ilegibles.append({"archivo": relativo, "error": "LECTURA"})
                continue
            archivos += 1
            hallazgos.extend(_ceros_de(arbol, relativo, permitidos))
    hallazgos.sort(key=lambda h: (h["archivo"], h["linea"], h["expresion"]))
    return {"archivos": archivos, "podados": sorted(podados), "ilegibles": ilegibles,
            "permitidos": sorted(permitidos), "hallazgos": hallazgos}


def salida(censo: dict) -> tuple:
    """El código de salida y su motivo, con la precedencia que ya declara `recibo.salida_global`.

    Un árbol sin un solo archivo legible es `2`, nunca `0`: `SIN_SUPERFICIE` es un hueco, no una
    limpia. Un hallazgo es `1` porque es accionable. Lo que no se pudo leer mantiene la corrida en
    `2`. El recibo publica las dos dimensiones a la vez para que un `1` no esconda su hueco.
    """
    if censo["archivos"] == 0 and not censo["ilegibles"]:
        return RC_HUECO, "SIN_SUPERFICIE"
    if censo["hallazgos"]:
        return RC_HALLAZGOS, "CON_HALLAZGOS"
    if censo["ilegibles"]:
        return RC_HUECO, "HUECO_DE_MEDICION"
    return RC_OK, "SIN_HALLAZGOS"


def texto(censo: dict) -> str:
    """La lectura humana del mismo objeto que consume `--json`."""
    codigo, motivo = salida(censo)
    lineas = [
        f"# Censo de ceros implícitos · `{motivo}` · RC `{codigo}`",
        "",
        f"archivos `{censo['archivos']}` · podados `{len(censo['podados'])}` · "
        f"ilegibles `{len(censo['ilegibles'])}` · permitidos `{len(censo['permitidos'])}` · "
        f"hallazgos `{len(censo['hallazgos'])}`",
    ]
    if censo["hallazgos"]:
        lineas += ["", "| archivo | línea | expresión |", "|---|---|---|"]
        lineas += [f"| `{h['archivo']}` | {h['linea']} | `{h['expresion']}` |"
                   for h in censo["hallazgos"]]
    if censo["ilegibles"]:
        lineas += ["", "| archivo | error |", "|---|---|"]
        lineas += [f"| `{i['archivo']}` | {i['error']} |" for i in censo["ilegibles"]]
    if censo["podados"]:
        lineas += ["", "Podados: " + ", ".join(f"`{p}`" for p in censo["podados"])]
    return "\n".join(lineas) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ceros-implicitos",
        description="Censo de ceros escritos a mano sobre un árbol, con su dominio declarado.")
    parser.add_argument("raiz", nargs="?", default=".", help="árbol a censar (por defecto .)")
    parser.add_argument("--permitidos", default="",
                        help="claves de get cuyo cero está declarado, separadas por comas")
    parser.add_argument("--excluir", default="",
                        help="patrones de directorio adicionales a podar, separados por comas")
    parser.add_argument("--json", action="store_true", help="publicar el censo canónico")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.raiz):
        print(f"ceros-implicitos: error: '{args.raiz}' no es un directorio", file=sys.stderr)
        return RC_ARIDAD

    censo = censar(args.raiz, permitidos=_conjunto(args.permitidos),
                   excluidos=EXCLUIDOS + tuple(_conjunto(args.excluir)))
    sys.stdout.write(canonico(censo) if args.json else texto(censo))
    return salida(censo)[0]


if __name__ == "__main__":
    raise SystemExit(main())
