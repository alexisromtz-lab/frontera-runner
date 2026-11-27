"""Four fake instruments and one throwaway subject, so the runner can be tested for real.

The composite runner's whole job is to survive instruments it does not control, so the tests do
not mock the boundary: they write four minimal packages that obey the same `-m module` invocation
form and the same exit codes, and they run them as subprocesses. A fake stops being a fake if the
runner can tell it apart from the real thing, which is the property that matters here.

Each fake reads `<subject>/.fake/<instrument>.json` to learn what to answer, because the
environment is allowlisted and the only channel the runner leaves open on purpose is the subject.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

MOLDE = '''"""{nombre}: fake instrument, invoked exactly like the real one."""
import json
import os
import sys
import time

NOMBRE = "{nombre}"
CFG = {{"rc": 0, "salida": {salida}, "sleep": 0}}
ruta = os.path.join(os.getcwd(), ".fake", NOMBRE + ".json")
if os.path.exists(ruta):
    with open(ruta, encoding="utf-8") as f:
        CFG.update(json.load(f))
if CFG.get("sleep"):
    time.sleep(CFG["sleep"])
if "crudo" in CFG:
    sys.stdout.write(CFG["crudo"])
else:
    sys.stdout.write(json.dumps(CFG.get("salida") or {{}}))
sys.exit(CFG["rc"])
'''

#: What a well-behaved fake answers by default: the keys the real instrument publishes.
#:
#: The detail lists are here on purpose. A real instrument publishes the names of what it counted,
#: and the runner refuses a count it cannot break into names, so a fake without them would be
#: testing a runner that accepts a number nobody can diff.
SALIDAS = {
    "git-complement-audit": {"counts": {"ORPHAN_CODE": 0, "ORPHAN_SECRET_RISK": 0,
                                        "HISTORY_SECRET_RISK": 0},
                             "findings": [],
                             "universe": {"paths": 0, "blobs_outside_head": 0},
                             "repo": {"refs": 1},
                             "age_strata": {"refs": {"live": 1, "recent": 0, "stale": 0,
                                                     "undated": 0},
                                            "live": 0, "recent": 0, "stale": 0,
                                            "history_only": 0, "conservation": True}},
    "fiber-ast-lint": {"archivos": 1, "for_medidos": 1, "candidatos": []},
    "test-ordinal-ratchet": {"files": 1, "parsed": 1, "collisions": [],
                             "total": {"ordinal": 0, "shadow": 0, "shared": 0}},
    "ts-py-anchor-guard": {"totales": {"pares": 1, "comparadas": 1, "declaradas": 1,
                                       "divergen": 0, "no_medidos": 0},
                           "pares": [{"nombre": "vista", "rc": 0, "anclas": []}]},
}

#: One faithful finding per instrument, used by the differential tests to build two receipts that
#: differ by exactly what a pull request would change.
HALLAZGOS = {
    "git-complement-audit": [{"class": "ORPHAN_CODE", "path": "src/huerfano.py",
                              "root": "refs", "oid": "0" * 40, "size": 10}],
    "fiber-ast-lint": [{"archivo": "src/fibra.py", "qualname": "f", "familia": "G",
                        "forma": "NORMALIZA", "poblacion": "PROYECCION", "linea": 7}],
    "test-ordinal-ratchet": [{"kind": "ordinal", "path": "tests/test_a.py", "scope": "module",
                              "name": "test_1_dos", "first": 1, "line": 9}],
    "ts-py-anchor-guard": [{"nombre": "vista", "rc": 1, "anclas": [{"ancla": "ALTO", "ok": False}],
                            "no_evaluables": []}],
}

#: The counter each instrument would publish for exactly one finding of `HALLAZGOS`.
UN_HALLAZGO = {
    "git-complement-audit": {"counts": {"ORPHAN_CODE": 1, "ORPHAN_SECRET_RISK": 0,
                                        "HISTORY_SECRET_RISK": 0}},
    "fiber-ast-lint": {"archivos": 1, "for_medidos": 1},
    "test-ordinal-ratchet": {"files": 1, "parsed": 1, "total": {"ordinal": 1, "shadow": 0,
                                                               "shared": 0}},
    "ts-py-anchor-guard": {"totales": {"pares": 1, "comparadas": 1, "declaradas": 1,
                                       "divergen": 1, "no_medidos": 0}},
}


def un_hallazgo(instrumento: str) -> dict:
    """A payload that declares exactly one finding, with its counter and its name."""
    salida = dict(SALIDAS[instrumento])
    clave = {"git-complement-audit": "findings", "fiber-ast-lint": "candidatos",
             "test-ordinal-ratchet": "collisions", "ts-py-anchor-guard": "pares"}[instrumento]
    salida.update(UN_HALLAZGO[instrumento])
    salida[clave] = HALLAZGOS[instrumento]
    if instrumento == "git-complement-audit":
        salida.update({"universe": {"paths": 1, "blobs_outside_head": 1},
                       "age_strata": {"refs": {"live": 1, "recent": 0, "stale": 0,
                                               "undated": 0},
                                      "live": 1, "recent": 0, "stale": 0,
                                      "history_only": 0, "conservation": True}})
    return salida

#: instrument name -> (path of the module file inside its repo, relative)
MODULOS = {
    "git-complement-audit": "git_complement_audit/__main__.py",
    "fiber-ast-lint": "src/fiber_ast_lint/cli.py",
    "test-ordinal-ratchet": "ordinal_ratchet/cli.py",
    "ts-py-anchor-guard": "ts_py_anchor_guard/anchor_oracle.py",
}

#: A different version per fake, so a receipt that swapped two identities would show.
VERSIONES = {
    "git-complement-audit": "9.0.1",
    "fiber-ast-lint": "9.0.2",
    "test-ordinal-ratchet": "9.0.3",
    "ts-py-anchor-guard": "9.0.4",
}

PAQUETES = {
    "git-complement-audit": "git_complement_audit",
    "fiber-ast-lint": "src/fiber_ast_lint",
    "test-ordinal-ratchet": "ordinal_ratchet",
    "ts-py-anchor-guard": "ts_py_anchor_guard",
}


#: Pinned so that two fixtures with the same content get the same commit. Without this the
#: commit digest of a fake repository depends on the second it was created in, and the receipt
#: would differ between two runs over the same bytes -- the exact defect the seal exists to deny.
EPOCA = "2021-01-01T00:00:00 +0000"
ENTORNO_GIT = {**os.environ,
               "GIT_AUTHOR_DATE": EPOCA, "GIT_COMMITTER_DATE": EPOCA,
               "GIT_AUTHOR_NAME": "f", "GIT_COMMITTER_NAME": "f",
               "GIT_AUTHOR_EMAIL": "f@f", "GIT_COMMITTER_EMAIL": "f@f"}


def git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True,
                   env=ENTORNO_GIT)


def crear_raiz(base: str, con_git: bool = True, versiones: dict | None = None) -> str:
    """Write the four fake instruments under `base` and return it.

    `con_git` commits them, because the identity law asks every executor for the commit of its
    repository: a fake without history is a fake the runner is right to reject. `versiones`
    overrides a version, which is how a test asks what the gate does when the instrument that
    spoke in base is not the instrument that spoke in head.
    """
    versiones = {**VERSIONES, **(versiones or {})}
    for nombre, relativa in MODULOS.items():
        paquete = os.path.join(base, nombre, PAQUETES[nombre])
        os.makedirs(paquete, exist_ok=True)
        with open(os.path.join(paquete, "__init__.py"), "w", encoding="utf-8") as f:
            f.write(f'__version__ = "{versiones[nombre]}"\n')
        destino = os.path.join(base, nombre, relativa)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            # `repr`, not `json.dumps`: this is Python source, and `true` is not a Python name.
            f.write(MOLDE.format(nombre=nombre, salida=repr(SALIDAS[nombre])))
    if con_git:
        git(base, "init", "-q", ".")
        git(base, "add", "-A")
        git(base, "-c", "user.email=f@f", "-c", "user.name=f", "commit", "-qm", "instrumentos")
    return base


class Sujeto:
    """A throwaway subject: a git tree, whatever files a test needs, and the fakes' answers."""

    def __init__(self, git_si: bool = True):
        self.ruta = tempfile.mkdtemp(prefix="frontera-sujeto-")
        if git_si:
            git(self.ruta, "init", "-q", ".")

    def escribir(self, relativa: str, contenido: str = "") -> str:
        destino = os.path.join(self.ruta, relativa)
        os.makedirs(os.path.dirname(destino) or self.ruta, exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(contenido)
        return destino

    def responder(self, instrumento: str, **cfg) -> None:
        self.escribir(os.path.join(".fake", instrumento + ".json"), json.dumps(cfg))

    def confirmar(self) -> None:
        if os.path.isdir(os.path.join(self.ruta, ".git")):
            git(self.ruta, "add", "-A")
            git(self.ruta, "-c", "user.email=s@s", "-c", "user.name=s", "commit", "-qm", "sujeto")

    def borrar(self) -> None:
        shutil.rmtree(self.ruta, ignore_errors=True)


def mixto(git_si: bool = True) -> Sujeto:
    """Python, a test file, TypeScript and a manifest: the shape that admits all four."""
    s = Sujeto(git_si=git_si)
    s.escribir("pkg/core.py", "def f(x):\n    return x\n")
    s.escribir("tests/test_core.py", "import unittest\n\n\nclass T(unittest.TestCase):\n"
                                     "    def test_a(self):\n        self.assertTrue(True)\n")
    s.escribir("src/engine.ts", "export const N = 3;\n")
    s.escribir("ts-py-anchor.json", json.dumps({"version": 1, "pares": []}))
    return s
