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

Un censo es un diagnóstico; un delta es una puerta. `delta(base, head)` resta dos censos por
**clase** de cero —archivo, clave y forma—, nunca por línea: mover una línea, o renombrar el
diccionario del que se lee, no añade un cero y no puede hacer fallar una compuerta. La clase es la
misma granularidad con la que `--permitidos` excusa: lo que se puede declarar por nombre se cuenta
por nombre.

`--permitidos` transporta nombres separados por comas. Una declaración que lleva una coma dentro
—`a.llamadas.get(k, 0)`— no cabe ahí: partirla la convierte en fragmentos que no casan con nada y
el censo publica un número de permitidos que se lee como declaración ejercida. Esa forma viaja por
`--permitir`, una por bandera, sin separador que la parta.

Una declaración se coteja como **expresión**, no como texto. `ast.unparse` devuelve una ortografía
—`d.get('k', 0)`— y el fuente guarda otra —`d.get("k", 0)`—; son el mismo nodo. Comparar texto
obligaba a adivinar la ortografía que el ejecutable eligió, y en el delta esa cadena no se publica:
medido el 28-Nov-2026 en un repo ajeno, la misma línea declarada tal como está escrita en el fuente
seguía dando RC 1. Ahora se compara el árbol de cada declaración, así que vale lo que un humano
copia del archivo.
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


def _forma(declaracion: str) -> str:
    """La huella de una declaración: su árbol si compila, su texto si no.

    Una clave —`nuevos`— no es una expresión y no compila como tal; se compara por texto. Una
    expresión se compara por árbol, para que la ortografía del fuente y la de `ast.unparse`
    sean la misma declaración.
    """
    try:
        return "AST:" + ast.dump(ast.parse(declaracion, mode="eval").body)
    except SyntaxError:
        return "TXT:" + declaracion


def _ceros_de(arbol, relativo: str, permitidos) -> list:
    """`permitidos` nombra lo declarado: la clave de un `get`, o la expresión de la línea.

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
        if expresion in permitidos or "AST:" + ast.dump(nodo) in permitidos:
            continue
        hallazgos.append({"archivo": relativo, "linea": nodo.lineno, "clave": clave,
                          "forma": "GET" if lectura else "OR", "expresion": expresion})
    return hallazgos


def censar(raiz, permitidos=frozenset(), excluidos=EXCLUIDOS) -> dict:
    """El censo de un árbol: sus hallazgos y el dominio exacto sobre el que valen.

    `permitidos` son nombres cuyo cero está declarado y no se cuenta: la clave de un `get` o la
    expresión exacta de la línea. Un `get` cuya clave no es una cadena literal publica
    `clave: null` y no se puede desactivar por clave: no hay nombre que declarar, así que tampoco
    hay clase que excusar — sólo la línea, si alguien la escribe entera.
    """
    raiz = os.path.abspath(raiz)
    declarados = frozenset(permitidos)
    cotejo = declarados | frozenset(_forma(p) for p in declarados)
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
            hallazgos.extend(_ceros_de(arbol, relativo, cotejo))
    hallazgos.sort(key=lambda h: (h["archivo"], h["linea"], h["expresion"]))
    return {"archivos": archivos, "podados": sorted(podados), "ilegibles": ilegibles,
            "permitidos": sorted(declarados), "hallazgos": hallazgos}


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


def _clase(hallazgo: dict) -> tuple:
    """Lo que un cero es cuando el árbol se mueve: dónde, sobre qué clave, de qué forma."""
    return (hallazgo["archivo"], hallazgo["clave"], hallazgo["forma"])


def _por_clase(censo: dict) -> dict:
    clases = {}
    for hallazgo in censo["hallazgos"]:
        clases.setdefault(_clase(hallazgo), []).append(hallazgo["linea"])
    return {clave: sorted(lineas) for clave, lineas in clases.items()}


def _dominio(censo: dict) -> dict:
    """El denominador de cada lado, en el mismo objeto que su resta: un delta sin él no vale."""
    return {"archivos": censo["archivos"], "hallazgos": len(censo["hallazgos"]),
            "ilegibles": len(censo["ilegibles"]), "podados": len(censo["podados"])}


def delta(base: dict, head: dict) -> dict:
    """Lo que el cambio añadió y lo que cerró, por clase de cero y no por línea.

    La resta es de multiconjuntos: un archivo con dos `get('nuevos', 0)` y luego tres tiene un
    cero nuevo, y uno con dos que sigue con dos no tiene ninguno aunque las líneas se hayan
    movido. Un cero que cambia de archivo es un cierre y una apertura, porque el archivo es parte
    de lo que el cero afirma.

    `lineas` publica las del lado que las conserva —head para lo nuevo, base para lo cerrado—, no
    las que llegaron: dos líneas idénticas son una sola clase, y con tres líneas en el archivo el
    censo no puede decir cuál de ellas es la que apareció. `veces` es el exceso, y es lo que cuenta.
    """
    clases_base = _por_clase(base)
    clases_head = _por_clase(head)
    nuevos = [{"archivo": clave[0], "clave": clave[1], "forma": clave[2],
               "veces": len(lineas) - len(clases_base.get(clave, [])), "lineas": lineas}
              for clave, lineas in clases_head.items() if len(lineas) > len(clases_base.get(clave, []))]
    cerrados = [{"archivo": clave[0], "clave": clave[1], "forma": clave[2],
                 "veces": len(lineas) - len(clases_head.get(clave, [])), "lineas": lineas}
                for clave, lineas in clases_base.items() if len(lineas) > len(clases_head.get(clave, []))]
    permanecen = sum(min(len(l), len(clases_head.get(c, []))) for c, l in clases_base.items())
    orden = lambda fila: (fila["archivo"], fila["clave"] or "", fila["forma"])
    return {"base": _dominio(base), "head": _dominio(head),
            "nuevos": sorted(nuevos, key=orden), "cerrados": sorted(cerrados, key=orden),
            "permanecen": permanecen}


def salida_delta(diferencia: dict) -> tuple:
    """El código de salida de la resta, con el hueco por delante del hallazgo.

    Un lado sin superficie, o con archivos que no se pudieron leer, deja la resta sin denominador:
    publicar `RC 0` porque `nuevos` quedó vacío sería leer un cálculo incompleto como una limpia.
    Por eso el hueco vence al hallazgo, al revés que en `salida` —donde el censo de un lado sí sabe
    cuántos hallazgos hay aunque haya un ilegible—, porque aquí lo que falta es el minuendo.
    """
    for lado in ("base", "head"):
        if diferencia[lado]["archivos"] == 0 and diferencia[lado]["ilegibles"] == 0:
            return RC_HUECO, "SIN_SUPERFICIE_EN_LA_BASE" if lado == "base" else "SIN_SUPERFICIE_EN_HEAD"
        if diferencia[lado]["ilegibles"]:
            return RC_HUECO, "HUECO_DE_MEDICION_EN_LA_BASE" if lado == "base" else "HUECO_DE_MEDICION_EN_HEAD"
    if diferencia["nuevos"]:
        return RC_HALLAZGOS, "CON_CEROS_NUEVOS"
    return RC_OK, "SIN_CEROS_NUEVOS"


def texto_delta(diferencia: dict) -> str:
    """La lectura humana de la resta, con los dos denominadores a la vista."""
    codigo, motivo = salida_delta(diferencia)
    nuevos = sum(fila["veces"] for fila in diferencia["nuevos"])
    cerrados = sum(fila["veces"] for fila in diferencia["cerrados"])
    lineas = [
        f"# Delta de ceros implícitos · `{motivo}` · RC `{codigo}`",
        "",
        f"nuevos `{nuevos}` · cerrados `{cerrados}` · permanecen `{diferencia['permanecen']}`",
        "",
        "| lado | archivos | hallazgos | ilegibles | podados |",
        "|---|---|---|---|---|",
    ]
    for lado in ("base", "head"):
        dominio = diferencia[lado]
        lineas.append(f"| `{lado}` | {dominio['archivos']} | {dominio['hallazgos']} | "
                      f"{dominio['ilegibles']} | {dominio['podados']} |")
    if diferencia["nuevos"]:
        lineas += ["", "| archivo | clave | forma | veces | líneas |", "|---|---|---|---|---|"]
        lineas += [f"| `{f['archivo']}` | `{f['clave']}` | {f['forma']} | {f['veces']} | "
                   f"{', '.join(str(n) for n in f['lineas'])} |" for f in diferencia["nuevos"]]
    return "\n".join(lineas) + "\n"


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
    parser.add_argument("--base", default=None,
                        help="árbol de la base; con --base, RAIZ es el head y se publica el delta")
    parser.add_argument("--permitidos", default="",
                        help="claves de get cuyo cero está declarado, separadas por comas; una "
                             "expresión que lleva coma no cabe aquí y va por --permitir")
    parser.add_argument("--permitir", action="append", default=[], metavar="EXPRESION",
                        help="una declaración literal por bandera, sin separador: es el canal de "
                             "las expresiones que llevan coma, como a.llamadas.get(k, 0)")
    parser.add_argument("--excluir", default="",
                        help="patrones de directorio adicionales a podar, separados por comas")
    parser.add_argument("--json", action="store_true", help="publicar el censo canónico")
    args = parser.parse_args(argv)

    for ruta in (args.raiz, args.base):
        if ruta is not None and not os.path.isdir(ruta):
            print(f"ceros-implicitos: error: '{ruta}' no es un directorio", file=sys.stderr)
            return RC_ARIDAD

    # Dos canales y no uno: `--permitidos` parte por coma, así que una expresión como
    # `a.m.get(k, 0)` llegaría rota. `--permitir` no parte nada.
    permitidos = _conjunto(args.permitidos) | frozenset(p.strip() for p in args.permitir
                                                         if p.strip())
    excluidos = EXCLUIDOS + tuple(_conjunto(args.excluir))
    if args.base is None:
        censo = censar(args.raiz, permitidos=permitidos, excluidos=excluidos)
        sys.stdout.write(canonico(censo) if args.json else texto(censo))
        return salida(censo)[0]
    diferencia = delta(censar(args.base, permitidos=permitidos, excluidos=excluidos),
                       censar(args.raiz, permitidos=permitidos, excluidos=excluidos))
    sys.stdout.write(canonico(diferencia) if args.json else texto_delta(diferencia))
    return salida_delta(diferencia)[0]


if __name__ == "__main__":
    raise SystemExit(main())
