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
SALIDAS = {
    "git-complement-audit": {"counts": {"ORPHAN_CODE": 0, "ORPHAN_SECRET_RISK": 0,
                                        "HISTORY_SECRET_RISK": 0},
                             "universe": {"paths": 0, "blobs_outside_head": 0},
                             "repo": {"refs": 1},
                             "age_strata": {"refs": {"live": 1, "recent": 0, "stale": 0,
                                                     "undated": 0},
                                            "live": 0, "recent": 0, "stale": 0,
                                            "history_only": 0, "conservation": True}},
    "fiber-ast-lint": {"archivos": 1, "for_medidos": 1, "candidatos": []},
    "test-ordinal-ratchet": {"files": 1, "parsed": 1,
                             "total": {"ordinal": 0, "shadow": 0, "shared": 0}},
    "ts-py-anchor-guard": {"totales": {"pares": 1, "comparadas": 1, "declaradas": 1,
                                       "divergen": 0, "no_medidos": 0}},
}

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


def git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True)


def crear_raiz(base: str, con_git: bool = True) -> str:
    """Write the four fake instruments under `base` and return it.

    `con_git` commits them, because the identity law asks every executor for the commit of its
    repository: a fake without history is a fake the runner is right to reject.
    """
    for nombre, relativa in MODULOS.items():
        paquete = os.path.join(base, nombre, PAQUETES[nombre])
        os.makedirs(paquete, exist_ok=True)
        with open(os.path.join(paquete, "__init__.py"), "w", encoding="utf-8") as f:
            f.write(f'__version__ = "{VERSIONES[nombre]}"\n')
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
