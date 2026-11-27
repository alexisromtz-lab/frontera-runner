"""What the composite runner promises, checked against four instruments it does not control."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import apoyo  # noqa: E402

from frontera_runner import instrumentos as inst  # noqa: E402
from frontera_runner import cli, recibo, render, runner  # noqa: E402


class Base(unittest.TestCase):
    """One fake instrument fleet for the whole module: the runner is measured, not re-wired."""

    @classmethod
    def setUpClass(cls):
        cls.caja = tempfile.mkdtemp(prefix="frontera-raiz-")
        cls.raiz = apoyo.crear_raiz(cls.caja)
        cls.sujetos = []

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls.caja, ignore_errors=True)
        for sujeto in cls.sujetos:
            sujeto.borrar()

    def sujeto(self, **kwargs):
        s = apoyo.mixto(**kwargs)
        self.sujetos.append(s)
        return s

    def vacio(self, git_si: bool = False):
        s = apoyo.Sujeto(git_si=git_si)
        self.sujetos.append(s)
        return s

    def medir(self, sujeto, **kwargs):
        return recibo.construir(sujeto.ruta, self.raiz, **kwargs)

    def ejecutor(self, recibo_, nombre):
        return recibo_["ejecutores"][nombre]


class Triaje(Base):
    """H0_Triaje_Admision: an absent universe is refused by name, never counted as zero."""

    def test_sujeto_vacio_no_es_un_cero_verde(self):
        s = self.vacio()
        r = self.medir(s)
        self.assertEqual(r["denominador"]["aplicables"], 0)
        self.assertEqual(r["denominador"]["no_aplicables"], 4)
        self.assertEqual(recibo.salida_global(r), (2, "SIN_SUPERFICIE"))
        for nombre, registro in r["ejecutores"].items():
            self.assertEqual(registro["estado"], runner.NO_APLICABLE, nombre)
            self.assertIsNone(registro["hallazgos"], nombre)
            self.assertTrue(registro["razon"], nombre)

    def test_razones_declaradas_por_instrumento(self):
        s = self.sujeto(git_si=True)
        os.remove(os.path.join(s.ruta, "src", "engine.ts"))
        os.remove(os.path.join(s.ruta, "ts-py-anchor.json"))
        os.remove(os.path.join(s.ruta, "tests", "test_core.py"))
        r = self.medir(s)
        self.assertEqual(self.ejecutor(r, "ts-py-anchor-guard")["razon"], "SIN_SUPERFICIE_TYPESCRIPT")
        self.assertEqual(self.ejecutor(r, "test-ordinal-ratchet")["razon"], "SIN_ARCHIVOS_DE_PRUEBA")
        self.assertEqual(self.ejecutor(r, "fiber-ast-lint")["estado"], runner.APLICABLE)

    def test_typescript_sin_manifiesto_es_no_aplicable(self):
        s = self.sujeto()
        os.remove(os.path.join(s.ruta, "ts-py-anchor.json"))
        r = self.medir(s)
        registro = self.ejecutor(r, "ts-py-anchor-guard")
        self.assertEqual(registro["estado"], runner.NO_APLICABLE)
        self.assertEqual(registro["razon"], "SIN_MANIFIESTO_DE_ANCLA")

    def test_sin_arbol_git_el_auditor_no_se_ejecuta(self):
        s = self.sujeto()
        import shutil

        shutil.rmtree(os.path.join(s.ruta, ".git"))
        s.escribir("pkg/core.py", "def f(x):\n    return x\n")
        r = self.medir(s)
        self.assertEqual(self.ejecutor(r, "git-complement-audit")["razon"], "SIN_ARBOL_GIT")

    def test_sin_python_no_se_admite_fibra(self):
        s = self.sujeto()
        os.remove(os.path.join(s.ruta, "pkg", "core.py"))
        os.remove(os.path.join(s.ruta, "tests", "test_core.py"))
        r = self.medir(s)
        self.assertEqual(self.ejecutor(r, "fiber-ast-lint")["razon"], "SIN_SUPERFICIE_PYTHON")

    def test_forzado_corre_los_cuatro_y_lo_dice(self):
        s = self.vacio()
        r = self.medir(s, forzar=True)
        self.assertEqual(r["modo"], "FORZADO")
        self.assertEqual(r["denominador"]["aplicables"], 4)
        self.assertTrue(all(e["rc"] is not None for e in r["ejecutores"].values()))


class ContratoDeRC(Base):
    """The mapping from an instrument's exit code to a state, including the trap in it."""

    def test_sin_sujeto_del_instrumento_no_es_cero_hallazgos(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=2)
        r = self.medir(s)
        registro = self.ejecutor(r, "fiber-ast-lint")
        self.assertEqual(registro["estado"], runner.NO_APLICABLE)
        self.assertTrue(registro["razon"].startswith("EL_INSTRUMENTO_NO_VIO_SUJETO"))
        self.assertIsNone(registro["hallazgos"])
        self.assertEqual(r["denominador"]["con_hallazgos"], 0)
        self.assertEqual(r["denominador"]["sin_hallazgos"], 3)

    def test_ordinal_sin_sujeto_tampoco(self):
        s = self.sujeto()
        s.responder("test-ordinal-ratchet", rc=2)
        r = self.medir(s)
        self.assertEqual(self.ejecutor(r, "test-ordinal-ratchet")["estado"], runner.NO_APLICABLE)

    def test_no_medido_se_declara_y_no_vota_verde(self):
        s = self.sujeto()
        s.responder("git-complement-audit", rc=2)
        r = self.medir(s)
        registro = self.ejecutor(r, "git-complement-audit")
        self.assertEqual(registro["estado"], runner.NO_MEDIDO)
        self.assertEqual(registro["razon"], "repositorio o argumentos invalidos")
        self.assertEqual(recibo.salida_global(r), (2, "HUECO_DE_MEDICION"))

    def test_la_particion_de_edad_viaja_en_el_recibo(self):
        r = self.medir(self.sujeto())
        denominador = self.ejecutor(r, "git-complement-audit")["denominador"]
        self.assertEqual(denominador["refs_vivas_30d"], 1)
        self.assertEqual(denominador["refs_recientes_90d"], 0)
        self.assertEqual(denominador["refs_inactivas"], 0)
        self.assertIs(denominador["estratos_reconcilian"], True)

    def test_sin_particion_de_edad_es_no_medido(self):
        s = self.sujeto()
        s.responder("git-complement-audit", rc=0, salida={"universe": {"paths": 0},
                                                          "repo": {"refs": 2},
                                                          "counts": {"ORPHAN_CODE": 0,
                                                                     "ORPHAN_SECRET_RISK": 0,
                                                                     "HISTORY_SECRET_RISK": 0}})
        r = self.medir(s)
        denominador = self.ejecutor(r, "git-complement-audit")["denominador"]
        self.assertEqual(denominador["refs"], 2)
        self.assertIsNone(denominador["refs_vivas_30d"])
        self.assertIn("refs_vivas_30d=`NO_MEDIDO`", render.markdown(r))

    def test_rc_no_declarado_no_se_adivina(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=7)
        r = self.medir(s)
        self.assertEqual(self.ejecutor(r, "fiber-ast-lint")["razon"], "RC_NO_DECLARADO")

    def test_rc_de_medido_sin_contadores_no_es_un_cero(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=0, salida={"archivos": 1})
        r = self.medir(s)
        registro = self.ejecutor(r, "fiber-ast-lint")
        self.assertEqual(registro["estado"], runner.NO_MEDIDO)
        self.assertEqual(registro["razon"], "SALIDA_SIN_HALLAZGOS_DECLARADOS")
        self.assertIsNone(registro["hallazgos"])
        self.assertEqual(r["denominador"]["aplicables"], 3)

    def test_salida_ilegible_no_es_un_cero(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=0, crudo="no soy json")
        r = self.medir(s)
        registro = self.ejecutor(r, "fiber-ast-lint")
        self.assertEqual(registro["razon"], "SALIDA_NO_JSON")
        self.assertIsNone(registro["hallazgos"])

    def test_tiempo_agotado(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", sleep=3)
        r = self.medir(s, tiempo_limite=1)
        registro = self.ejecutor(r, "fiber-ast-lint")
        self.assertEqual(registro["estado"], runner.NO_MEDIDO)
        self.assertEqual(registro["razon"], "TIEMPO_AGOTADO")

    def test_hallazgos_y_denominador_se_leen_del_payload(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=1, salida={
            "archivos": 3, "for_medidos": 5, "candidatos": [{"a": 1}, {"b": 2}]})
        r = self.medir(s)
        registro = self.ejecutor(r, "fiber-ast-lint")
        self.assertEqual(registro["estado"], runner.APLICABLE)
        self.assertEqual(registro["hallazgos"], 2)
        self.assertEqual(registro["denominador"], {"archivos_python": 3, "sitios_medidos": 5})
        self.assertEqual(recibo.salida_global(r), (1, "CON_HALLAZGOS"))

    def test_instrumento_ausente(self):
        caja = tempfile.mkdtemp(prefix="frontera-parcial-")
        try:
            apoyo.crear_raiz(caja, con_git=False)
            import shutil

            shutil.rmtree(os.path.join(caja, "fiber-ast-lint"))
            s = self.sujeto()
            r = recibo.construir(s.ruta, caja)
            registro = r["ejecutores"]["fiber-ast-lint"]
            self.assertEqual(registro["estado"], runner.NO_EJECUTADO)
            self.assertEqual(registro["razon"], "INSTRUMENTO_AUSENTE")
            self.assertIn(recibo.salida_global(r)[0], (2, 3))
        finally:
            import shutil

            shutil.rmtree(caja, ignore_errors=True)


class Identidades(Base):
    """H0_Recibo_Unificado_PR: seal, determinism, declared identities, bounded render."""

    def test_dos_corridas_byte_a_byte(self):
        s = self.sujeto()
        primera = recibo.canonico(self.medir(s))
        segunda = recibo.canonico(self.medir(s))
        self.assertEqual(primera, segunda)

    def test_sello_recompone_y_detecta_manipulacion(self):
        r = self.medir(self.sujeto())
        self.assertTrue(recibo.verificar(r))
        roto = json.loads(recibo.canonico(r))
        roto["denominador"]["aplicables"] += 1
        self.assertFalse(recibo.verificar(roto))
        self.assertEqual(recibo.salida_global(roto), (3, "RECIBO_INCONSISTENTE"))

    def test_cada_ejecutor_declara_version_commit_y_huella(self):
        r = self.medir(self.sujeto())
        for nombre, registro in r["ejecutores"].items():
            self.assertEqual(registro["version"], apoyo.VERSIONES[nombre], nombre)
            self.assertRegex(registro["commit"] or "", r"^[0-9a-f]{40}$", nombre)
            self.assertRegex(registro["huella"] or "", r"^sha256:[0-9a-f]{64}$", nombre)
        self.assertTrue(r["leyes"]["identidad_de_ejecutores"])

    def test_leyes_cierran(self):
        r = self.medir(self.sujeto())
        for nombre, valor in r["leyes"].items():
            if isinstance(valor, bool):
                self.assertTrue(valor, nombre)
        self.assertEqual(r["leyes"]["suma_estados"], 4)

    def test_el_recibo_no_lleva_rutas_de_esta_maquina(self):
        s = self.sujeto()
        r = self.medir(s)
        texto = recibo.canonico(r)
        self.assertNotIn(s.ruta, texto)
        self.assertNotIn(self.caja, texto)

    def test_markdown_cabe_y_nombra_las_razones(self):
        s = self.sujeto()
        os.remove(os.path.join(s.ruta, "ts-py-anchor.json"))
        texto = render.markdown(self.medir(s))
        self.assertLess(len(texto), render.TOPE)
        for nombre in inst.POR_NOMBRE:
            self.assertIn(f"`{nombre}`", texto)
        self.assertIn("SIN_MANIFIESTO_DE_ANCLA", texto)

    def test_recorte_declarado_bajo_el_techo(self):
        largo = "\n".join(f"linea {i} de relleno" for i in range(20_000)) + "\n"
        corto = render.recortar(largo, tope=4_000)
        self.assertLessEqual(len(corto), 4_000)
        self.assertIn("RECORTADO", corto)
        self.assertEqual(render.recortar("hola\n", tope=4_000), "hola\n")


class LineaDeComandos(Base):
    """The exit codes the GitHub App reads; bad invocation is not a verdict on the subject."""

    def correr(self, *args):
        with tempfile.TemporaryDirectory() as caja:
            salida = os.path.join(caja, "out.txt")
            with open(salida, "w", encoding="utf-8") as f:
                guardado = sys.stdout, sys.stderr
                sys.stdout = sys.stderr = f
                try:
                    rc = cli.main(list(args))
                finally:
                    sys.stdout, sys.stderr = guardado
            with open(salida, encoding="utf-8") as f:
                return rc, f.read()

    def test_sujeto_limpio_y_con_hallazgos(self):
        s = self.sujeto()
        self.assertEqual(self.correr(s.ruta, "--raiz", self.raiz)[0], 0)
        s.responder("fiber-ast-lint", rc=1, salida={"archivos": 1, "for_medidos": 1,
                                                    "candidatos": [1]})
        self.assertEqual(self.correr(s.ruta, "--raiz", self.raiz)[0], 1)

    def test_sin_superficie_es_dos(self):
        s = self.vacio()
        self.assertEqual(self.correr(s.ruta, "--raiz", self.raiz)[0], 2)

    def test_aridad_invalida_es_veinte(self):
        self.assertEqual(self.correr(".", "--raiz", self.raiz, "--tiempo-limite", "0")[0], 20)

    def test_json_y_markdown_se_escriben(self):
        s = self.sujeto()
        with tempfile.TemporaryDirectory() as caja:
            ruta_json = os.path.join(caja, "r.json")
            ruta_md = os.path.join(caja, "r.md")
            rc, texto = self.correr(s.ruta, "--raiz", self.raiz, "--json",
                                    "--recibo", ruta_json, "--md", ruta_md)
            self.assertEqual(rc, 0)
            with open(ruta_json, encoding="utf-8") as f:
                self.assertTrue(recibo.verificar(json.load(f)))
            with open(ruta_md, encoding="utf-8") as f:
                self.assertTrue(f.read().startswith("# Frontera"))

    def test_self_test(self):
        self.assertEqual(cli.main(["--self-test"]), 0)


class Huellas(unittest.TestCase):
    """The fingerprint helpers, where a silent `None` would weaken every row above."""

    def test_version_desde_pyproject_y_desde_el_paquete(self):
        with tempfile.TemporaryDirectory() as caja:
            os.makedirs(os.path.join(caja, "pkg"))
            with open(os.path.join(caja, "pkg", "__init__.py"), "w", encoding="utf-8") as f:
                f.write('__version__ = "3.1.4"\n')
            self.assertEqual(inst.version_de(caja, "pkg"), "3.1.4")
            with open(os.path.join(caja, "pyproject.toml"), "w", encoding="utf-8") as f:
                f.write('[project]\nname = "x"\nversion = "5.0.0"\n')
            self.assertEqual(inst.version_de(caja, "pkg"), "5.0.0")

    def test_version_ausente_es_no_medido_y_no_una_cadena_vacia(self):
        with tempfile.TemporaryDirectory() as caja:
            self.assertIsNone(inst.version_de(caja, "pkg"))

    def test_huella_cambia_con_el_contenido(self):
        with tempfile.TemporaryDirectory() as caja:
            os.makedirs(os.path.join(caja, "pkg"))
            ruta = os.path.join(caja, "pkg", "a.py")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("x = 1\n")
            una = inst.huella_de(caja, "pkg")
            self.assertEqual(una, inst.huella_de(caja, "pkg"))
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("x = 2\n")
            self.assertNotEqual(una, inst.huella_de(caja, "pkg"))
            self.assertIsNone(inst.huella_de(caja, "no-existe"))

    def test_la_raiz_por_defecto_es_el_padre_del_repositorio(self):
        """Sibling-clone convention: one level up is where the instruments live, not this repo."""
        raiz = runner.raiz_por_defecto()
        repo = os.path.dirname(os.path.dirname(os.path.abspath(runner.__file__)))
        self.assertEqual(raiz, os.path.dirname(repo))
        self.assertTrue(os.path.isdir(os.path.join(raiz, os.path.basename(repo))))


if __name__ == "__main__":
    unittest.main()
