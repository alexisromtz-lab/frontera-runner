"""What the composite runner promises, checked against four instruments it does not control."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock

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
        dos = apoyo.HALLAZGOS["fiber-ast-lint"][0]
        s.responder("fiber-ast-lint", rc=1, salida={
            "archivos": 3, "for_medidos": 5,
            "candidatos": [dos, dict(dos, qualname="g")]})
        r = self.medir(s)
        registro = self.ejecutor(r, "fiber-ast-lint")
        self.assertEqual(registro["estado"], runner.APLICABLE)
        self.assertEqual(registro["hallazgos"], 2)
        self.assertEqual(registro["denominador"], {"archivos_python": 3, "sitios_medidos": 5})
        self.assertEqual(recibo.salida_global(r), (1, "CON_HALLAZGOS"))

    def test_contador_sin_nombres_no_es_un_numero_que_se_pueda_restar(self):
        """A count the runner cannot break into names is a number no diff can act on."""
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=1, salida={"archivos": 1, "for_medidos": 1,
                                                    "candidatos": [{"a": 1}]})
        registro = self.ejecutor(self.medir(s), "fiber-ast-lint")
        self.assertEqual(registro["estado"], runner.NO_MEDIDO)
        self.assertEqual(registro["razon"], "SALIDA_SIN_IDENTIDADES")
        self.assertIsNone(registro["hallazgos"])
        self.assertEqual(registro["hallazgos_declarados"], 1)

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
        s.responder("fiber-ast-lint", rc=1,
                    salida=apoyo.un_hallazgo("fiber-ast-lint"))
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


class ConsumidorDiferencial(Base):
    """H0_Consumidor_Diferencial: the seal is a gate only when something recomputes it and diffs.

    Every case here is a pull request: base is measured, the fake answers change the way a patch
    would change a real subject, and head is measured again over the same runner.
    """

    def par(self, **respuestas):
        """Base measured with the default answers, head measured after `respuestas`."""
        s = self.sujeto()
        base = self.medir(s)
        for nombre, cfg in respuestas.items():
            s.responder(nombre, **cfg)
        return base, self.medir(s)

    def fila(self, delta, nombre):
        return delta["instrumentos"][nombre]

    def test_dos_recibos_iguales_no_son_regresion(self):
        base, head = self.par()
        delta = recibo.comparar(base, head)
        self.assertEqual(delta["resumen"]["nuevos"], 0)
        self.assertEqual(delta["resumen"]["resueltos"], 0)
        self.assertEqual((delta["rc"], delta["veredicto"]), (0, "SIN_REGRESION"))

    def test_una_superficie_nueva_con_hallazgo_es_regresion(self):
        """Adding the first TypeScript file that diverges from its port is the change's fault.

        Measured 27-Nov-2026 in Actions (corrida 46076223056): the pull request added a TypeScript
        file with a diverging anchor and the check reported `SIN_REGRESION`. Base had answered
        `NO_APLICABLE` -- "nothing of mine to measure", a measurement of absence -- and the diff
        read it as a hole. A hole is `NO_MEDIDO`; an absence that this change fills is a surface
        the change creates, and what fails on it is new.
        """
        s = self.vacio(git_si=True)
        s.escribir("pkg/core.py", "def f(x):\n    return x\n")
        base = self.medir(s)
        self.assertEqual(self.ejecutor(base, "ts-py-anchor-guard")["estado"], runner.NO_APLICABLE)
        s.escribir("src/engine.ts", "export const N = 3;\n")
        s.escribir("ts-py-anchor.json", "{}")
        s.responder("ts-py-anchor-guard", rc=1, salida=apoyo.un_hallazgo("ts-py-anchor-guard"))
        delta = recibo.comparar(base, self.medir(s))
        fila = self.fila(delta, "ts-py-anchor-guard")
        self.assertEqual(fila["nota"], "SUPERFICIE_NUEVA")
        self.assertEqual(len(fila["nuevos"]), 1)
        self.assertIs(fila["atribuible"], True)
        self.assertEqual(delta["resumen"]["superficies_nuevas"], 1)
        self.assertEqual((delta["rc"], delta["veredicto"]), (1, "REGRESION"))

    def test_sin_base_medida_no_se_atribuye(self):
        """A hole in base is not an absence: its findings may predate the pull request."""
        s = self.sujeto()
        s.responder("ts-py-anchor-guard", rc=2)
        base = self.medir(s)
        self.assertEqual(self.ejecutor(base, "ts-py-anchor-guard")["estado"], runner.NO_MEDIDO)
        s.responder("ts-py-anchor-guard", rc=1, salida=apoyo.un_hallazgo("ts-py-anchor-guard"))
        delta = recibo.comparar(base, self.medir(s))
        fila = self.fila(delta, "ts-py-anchor-guard")
        self.assertEqual(fila["nota"], "SIN_BASE_MEDIDA")
        self.assertEqual(fila["nuevos"], [])
        self.assertEqual(delta["resumen"]["superficies_nuevas"], 0)
        self.assertEqual((delta["rc"], delta["veredicto"]), (0, "SIN_REGRESION"))

    def test_un_byte_manipulado_es_rc_tres(self):
        base, head = self.par()
        manipulado = json.loads(recibo.canonico(head))
        self.assertTrue(recibo.verificar(manipulado))
        manipulado["ejecutores"]["fiber-ast-lint"]["hallazgos"] += 1
        delta = recibo.comparar(base, manipulado)
        self.assertFalse(delta["verificacion"]["head"])
        self.assertEqual((delta["rc"], delta["veredicto"]), (3, "SELLO_NO_RECOMPONE"))
        self.assertIn("NO RECOMPONE", render.markdown_diff(delta))

    def test_hallazgo_preexistente_no_es_regresion(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=1, salida=apoyo.un_hallazgo("fiber-ast-lint"))
        base = self.medir(s)
        head = self.medir(s)
        delta = recibo.comparar(base, head)
        self.assertEqual(len(self.fila(delta, "fiber-ast-lint")["nuevos"]), 0)
        self.assertEqual(delta["rc"], 0)

    def test_hallazgo_nuevo_en_head_es_rc_uno_y_se_nombra(self):
        base, head = self.par(**{"fiber-ast-lint": dict(
            rc=1, salida=apoyo.un_hallazgo("fiber-ast-lint"))})
        delta = recibo.comparar(base, head)
        fila = self.fila(delta, "fiber-ast-lint")
        self.assertEqual(len(fila["nuevos"]), 1)
        self.assertIn("src/fibra.py", fila["nuevos"][0])
        self.assertEqual((delta["rc"], delta["veredicto"]), (1, "REGRESION"))
        self.assertIn("src/fibra.py", render.markdown_diff(delta))

    def test_resuelto_deja_el_veredicto_en_cero(self):
        s = self.sujeto()
        s.responder("fiber-ast-lint", rc=1, salida=apoyo.un_hallazgo("fiber-ast-lint"))
        base = self.medir(s)
        s.responder("fiber-ast-lint", rc=0, salida=apoyo.SALIDAS["fiber-ast-lint"])
        delta = recibo.comparar(base, self.medir(s))
        self.assertEqual(len(self.fila(delta, "fiber-ast-lint")["resueltos"]), 1)
        self.assertEqual(delta["rc"], 0)

    def test_perdida_de_medicion_no_se_lee_como_resuelto(self):
        """The trap: delete the anchor manifest and the guard stops counting. That is not a fix."""
        s = self.sujeto()
        s.responder("ts-py-anchor-guard", rc=1, salida=apoyo.un_hallazgo("ts-py-anchor-guard"))
        s.responder("fiber-ast-lint", rc=1, salida=apoyo.un_hallazgo("fiber-ast-lint"))
        base = self.medir(s)
        s.responder("ts-py-anchor-guard", rc=2)
        delta = recibo.comparar(base, self.medir(s))
        fila = self.fila(delta, "ts-py-anchor-guard")
        self.assertEqual(fila["nota"], "PERDIDA_DE_MEDICION")
        self.assertEqual(fila["resueltos"], [])
        self.assertEqual(fila["nuevos"], [])
        self.assertEqual((delta["rc"], delta["veredicto"]), (2, "PERDIDA_DE_MEDICION"))

    def test_el_guardián_reconcilia_por_partición_de_pares(self):
        """Its counter counts pars, not anchors: one par with two broken anchors is one."""
        s = self.sujeto()
        par = {"nombre": "vista", "rc": 1,
               "anclas": [{"ancla": "ALTO", "ok": False}, {"ancla": "BAJO", "ok": False}],
               "no_evaluables": []}
        salida = dict(apoyo.SALIDAS["ts-py-anchor-guard"], pares=[par],
                      totales={"pares": 1, "comparadas": 1, "declaradas": 2, "divergen": 1,
                               "no_medidos": 0})
        s.responder("ts-py-anchor-guard", rc=1, salida=salida)
        registro = self.ejecutor(self.medir(s), "ts-py-anchor-guard")
        self.assertEqual(registro["estado"], runner.APLICABLE)
        self.assertEqual(registro["hallazgos"], 2)
        self.assertEqual(registro["hallazgos_declarados"], 1)
        self.assertEqual(registro["unidad_declarada"], "par")
        self.assertTrue(registro["identidades_reconcilian"])

    def test_un_par_limpio_que_nombra_un_hallazgo_no_reconcilia(self):
        s = self.sujeto()
        par = {"nombre": "vista", "rc": 0, "anclas": [{"ancla": "ALTO", "ok": False}],
               "no_evaluables": []}
        salida = dict(apoyo.SALIDAS["ts-py-anchor-guard"], pares=[par])
        s.responder("ts-py-anchor-guard", rc=0, salida=salida)
        registro = self.ejecutor(self.medir(s), "ts-py-anchor-guard")
        self.assertEqual(registro["estado"], runner.NO_MEDIDO)
        self.assertEqual(registro["razon"], "IDENTIDADES_NO_RECONCILIAN")

    def test_delta_producido_por_otra_version_no_es_del_pr(self):
        caja = tempfile.mkdtemp(prefix="frontera-otra-version-")
        try:
            otra = apoyo.crear_raiz(os.path.join(caja, "v2"),
                                    versiones={"fiber-ast-lint": "9.9.9"})
            s = self.sujeto()
            base = self.medir(s)
            s.responder("fiber-ast-lint", rc=1, salida=apoyo.un_hallazgo("fiber-ast-lint"))
            head = recibo.construir(s.ruta, otra)
            delta = recibo.comparar(base, head)
            fila = self.fila(delta, "fiber-ast-lint")
            self.assertEqual(fila["nota"], "IDENTIDAD_DEL_EJECUTOR_DISTINTA")
            self.assertFalse(fila["atribuible"])
            self.assertEqual(delta["resumen"]["nuevos"], 0)
            self.assertEqual((delta["rc"], delta["veredicto"]), (2, "DELTA_NO_ATRIBUIBLE"))
        finally:
            import shutil

            shutil.rmtree(caja, ignore_errors=True)

    def test_esquemas_distintos_no_se_comparan(self):
        """A v1 receipt is re-sealed by hand here: the point is that its seal is good and it
        still cannot be differenced. A v1 body with a v2 seal is caught one step earlier."""
        base, head = self.par()

        def sellar_v1(cuerpo):
            viejo = json.loads(recibo.canonico(cuerpo))
            viejo["schema"] = 1
            sin_sello = {k: v for k, v in viejo.items() if k != "sello"}
            viejo["sello"] = recibo.sha256_de(recibo.canonico(sin_sello).encode("utf-8"))
            self.assertTrue(recibo.verificar(viejo))
            return viejo

        solo_head = recibo.comparar(base, sellar_v1(head))
        self.assertEqual((solo_head["rc"], solo_head["veredicto"]), (3, "ESQUEMAS_DISTINTOS"))
        ambos = recibo.comparar(sellar_v1(base), sellar_v1(head))
        self.assertEqual((ambos["rc"], ambos["veredicto"]), (3, "RECIBO_NO_COMPARABLE"))
        manipulado = json.loads(recibo.canonico(head))
        manipulado["schema"] = 1
        self.assertEqual(recibo.comparar(base, manipulado)["veredicto"], "SELLO_NO_RECOMPONE")

    def test_markdown_del_diff_cabe_bajo_el_techo(self):
        muchos = [dict(apoyo.HALLAZGOS["git-complement-audit"][0], path=f"src/h{i}.py")
                  for i in range(400)]
        salida = dict(apoyo.un_hallazgo("git-complement-audit"), findings=muchos,
                      counts={"ORPHAN_CODE": 400, "ORPHAN_SECRET_RISK": 0,
                              "HISTORY_SECRET_RISK": 0})
        base, head = self.par(**{"git-complement-audit": dict(rc=1, salida=salida)})
        delta = recibo.comparar(base, head)
        self.assertEqual(delta["resumen"]["nuevos"], 400)
        texto = render.markdown_diff(delta)
        self.assertLess(len(texto), render.TOPE)
        self.assertIn("más en el recibo JSON", texto)

    def test_el_comando_diff_devuelve_el_rc_del_veredicto(self):
        base, head = self.par(**{"fiber-ast-lint": dict(
            rc=1, salida=apoyo.un_hallazgo("fiber-ast-lint"))})
        with tempfile.TemporaryDirectory() as caja:
            ruta_base = recibo.escribir(base, os.path.join(caja, "base.json"))
            ruta_head = recibo.escribir(head, os.path.join(caja, "head.json"))
            ruta_md = os.path.join(caja, "diff.md")
            guardado = sys.stdout
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
            try:
                rc = cli.main(["diff", "--base", ruta_base, "--head", ruta_head, "--md", ruta_md])
            finally:
                sys.stdout.close()
                sys.stdout = guardado
            self.assertEqual(rc, 1)
            with open(ruta_md, encoding="utf-8") as f:
                self.assertIn("REGRESION", f.read())

    def test_diff_sin_recibo_legible_es_aridad(self):
        with tempfile.TemporaryDirectory() as caja:
            basura = os.path.join(caja, "basura.json")
            with open(basura, "w", encoding="utf-8") as f:
                f.write("no soy json")
            guardado = sys.stderr
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
            try:
                rc = cli.main(["diff", "--base", basura, "--head", basura])
            finally:
                sys.stderr.close()
                sys.stderr = guardado
            self.assertEqual(rc, cli.RC_ARIDAD)


class AutonomiaDeCI(unittest.TestCase):
    """H0_Autonomia_CI_Workflow and H0_Invarianza_Git_Vivo: outside this repository's parents.

    A consumer repository has no four sibling clones to point `--raiz` at, and a runner that only
    works beside its own colleagues is not a check anybody can install. These tests measure the
    two properties that make it installable, without a network: the resolution modes, and the
    dependence of the seal on paths rather than on the bytes.
    """

    @classmethod
    def setUpClass(cls):
        cls.cajas = []

    @classmethod
    def tearDownClass(cls):
        import shutil

        for caja in cls.cajas:
            shutil.rmtree(caja, ignore_errors=True)

    def caja(self, prefijo="frontera-ci-"):
        ruta = tempfile.mkdtemp(prefix=prefijo)
        self.cajas.append(ruta)
        return ruta

    def test_sin_raiz_el_paquete_instalado_es_una_resolucion(self):
        """`--raiz` absent means "find it": an installed package is found, not refused."""
        caja = self.caja()
        apoyo.crear_raiz(caja)
        instrumento = inst.POR_NOMBRE["fiber-ast-lint"]
        with unittest.mock.patch.object(inst, "ubicacion_instalada",
                                        return_value={"ruta": os.path.join(caja, "fiber-ast-lint",
                                                                           "src"),
                                                      "distribucion": "fiber-ast-lint",
                                                      "version": "9.0.2"}):
            with unittest.mock.patch.object(runner, "raiz_por_defecto",
                                            return_value=os.path.join(caja, "nadie")):
                resolucion = runner.resolver(instrumento)
        self.assertEqual(resolucion["modo"], runner.PAQUETE)
        self.assertIsNone(resolucion["repo"])
        self.assertEqual(resolucion["procedencia"], runner.PAQUETE)
        self.assertEqual(resolucion["version"], "9.0.2")
        self.assertIsNone(resolucion["commit"])
        self.assertRegex(resolucion["huella"], r"^sha256:[0-9a-f]{64}$")

    def test_un_paquete_instalado_no_lleva_pythonpath(self):
        """Setting one would shadow the installation with whatever sits beside this checkout."""
        entorno = runner.entorno_de(None)
        self.assertNotIn("PYTHONPATH", entorno)
        self.assertEqual(entorno["PYTHONHASHSEED"], "0")

    def test_raiz_explicita_no_sustituye_por_el_paquete_instalado(self):
        """A promise about where the instruments are is not renegotiated behind the caller."""
        caja = self.caja()
        instrumento = inst.POR_NOMBRE["fiber-ast-lint"]
        with unittest.mock.patch.object(inst, "ubicacion_instalada",
                                        side_effect=AssertionError("no debe sondearse")):
            resolucion = runner.resolver(instrumento, os.path.join(caja, "vacio"))
        self.assertIsNone(resolucion["repo"])
        self.assertEqual(resolucion["razon"], "INSTRUMENTO_AUSENTE")

    def test_un_pin_abreviado_verifica_el_commit_que_nombra(self):
        """A declaration is written the way `git rev-parse` reads it, or it verifies nothing."""
        instrumento = inst.POR_NOMBRE["git-complement-audit"]
        resolucion = {"version": "1.5.0", "commit": "1c73546fa" + "b" * 31,
                      "pin": {"commit": "1c73546fa", "version": "1.5.0"}}
        juicio = runner._juzgar_pin(instrumento, resolucion)
        self.assertEqual(juicio["estado"], "VERIFICADO")
        otro = dict(resolucion, commit="9" * 40)
        self.assertEqual(runner._juzgar_pin(instrumento, otro)["estado"], "DIVERGE")
        for corto in ("1c", "1c7354"):
            flojo = dict(resolucion, pin={"commit": corto})
            self.assertEqual(runner._juzgar_pin(instrumento, flojo)["estado"], "DIVERGE", corto)
        # An absent declaration is not a failed one: same word as an installation with no history.
        vacio = dict(resolucion, pin={"commit": ""})
        self.assertEqual(runner._juzgar_pin(instrumento, vacio)["estado"], "NO_VERIFICABLE")

    def test_una_instalacion_no_puede_verificar_un_commit_declarado(self):
        """`NO_VERIFICABLE` is its own word: an installation has no history to read."""
        instrumento = inst.POR_NOMBRE["fiber-ast-lint"]
        juicio = runner._juzgar_pin(instrumento, {"version": "0.5.0", "commit": None,
                                                  "pin": {"commit": "23dbf9a"}})
        self.assertEqual(juicio["estado"], "NO_VERIFICABLE")

    def test_un_paquete_sin_raiz_mide_en_vez_de_abortar(self):
        """The road without `--raiz` has no routes to scrub, and refusing them crashed the gate.

        Measured 27-Nov-2026 in Actions: without `--raiz`, the reason for a package whose module
        did not import was built by scrubbing `None`, which raised `TypeError` before the record
        existed -- so no head receipt was written and the diff failed with RC 20 on a subject
        that had never been measured.
        """
        caja = self.caja()
        apoyo.crear_raiz(caja)
        sujeto = apoyo.mixto()
        self.addCleanup(sujeto.borrar)
        instrumento = inst.POR_NOMBRE["fiber-ast-lint"]
        triaje = {i.nombre: {"estado": runner.APLICABLE, "razon": None, "insumos": {}}
                  for i in inst.INSTRUMENTOS}
        with unittest.mock.patch.object(inst, "ubicacion_instalada",
                                        return_value={"ruta": os.path.join(caja, "fiber-ast-lint",
                                                                           "src"),
                                                      "distribucion": "fiber-ast-lint",
                                                      "version": "9.0.2"}):
            with unittest.mock.patch.object(runner, "raiz_por_defecto",
                                            return_value=os.path.join(caja, "nadie")):
                registro = runner.ejecutar(instrumento, sujeto.ruta, None, triaje)
        self.assertEqual(registro["modo_resolucion"], runner.PAQUETE)
        self.assertEqual(registro["estado"], runner.NO_MEDIDO)
        self.assertTrue((registro["razon"] or "").startswith("SALIDA_NO_JSON"), registro["razon"])

    def test_la_ruta_del_paquete_no_entra_al_recibo(self):
        """A traceback from `site-packages` names this machine, so it is scrubbed like a subject."""
        limpio = runner._limpiar(
            "File /opt/hostedtoolcache/Python/3.12/site-packages/x.py no anda; sujeto /tmp/s",
            ("/tmp/s", "<sujeto>"), (None, "<herramientas>"),
            ("/opt/hostedtoolcache/Python/3.12/site-packages", "<paquete>"))
        self.assertNotIn("/opt/hostedtoolcache", limpio)
        self.assertNotIn("/tmp/s", limpio)
        self.assertIn("<paquete>", limpio)

    def test_las_leyes_aceptan_un_paquete_sin_commit_medido(self):
        base = {"ejecutores": {"x": {"estado": runner.APLICABLE, "version": "1.0",
                                     "huella": "sha256:" + "a" * 64, "commit": None,
                                     "procedencia": runner.PAQUETE, "hallazgos": 0,
                                     "huellas_de_hallazgo": [], "identidades_reconcilian": True,
                                     "razon": "limpio"}},
                "denominador": {}}
        self.assertTrue(recibo.leyes(base)["identidad_de_ejecutores"])
        sin_huella = json.loads(json.dumps(base))
        sin_huella["ejecutores"]["x"]["huella"] = None
        self.assertFalse(recibo.leyes(sin_huella)["identidad_de_ejecutores"])

    def test_dos_rutas_y_dos_raices_producen_el_mismo_sello(self):
        """H0_Invarianza_Git_Vivo: the digest depends on the bytes, not on where they landed."""
        caja = self.caja()
        origen = os.path.join(caja, "origen")
        apoyo.crear_raiz(os.path.join(caja, "herramientas-a"))
        apoyo.crear_raiz(os.path.join(caja, "ruta", "mucho", "mas", "larga", "herramientas-b"))
        os.makedirs(origen)
        apoyo.git(origen, "init", "-q", ".")
        for relativa, contenido in (("pkg/core.py", "def f(x):\n    return x\n"),
                                    ("tests/test_core.py", "import unittest\n"),
                                    ("src/engine.ts", "export const N = 3;\n"),
                                    ("ts-py-anchor.json", "{}")):
            destino = os.path.join(origen, relativa)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "w", encoding="utf-8") as f:
                f.write(contenido)
        apoyo.git(origen, "add", "-A")
        apoyo.git(origen, "-c", "user.email=s@s", "-c", "user.name=s", "commit", "-qm", "sujeto")
        apoyo.git(origen, "branch", "dev/viva")
        corto = os.path.join(caja, "a")
        largo = os.path.join(caja, "una", "ruta", "bastante", "mas", "profunda", "b")
        for destino in (corto, largo):
            apoyo.git(caja, "clone", "-q", origen, destino)

        primero = recibo.construir(corto, os.path.join(caja, "herramientas-a"))
        segundo = recibo.construir(largo, os.path.join(caja, "ruta", "mucho", "mas", "larga",
                                                      "herramientas-b"))
        self.assertTrue(recibo.verificar(primero) and recibo.verificar(segundo))
        self.assertEqual(recibo.canonico(primero), recibo.canonico(segundo))
        self.assertEqual(recibo.salida_global(primero), recibo.salida_global(segundo))
        for ruta in (corto, largo, caja):
            self.assertNotIn(ruta, recibo.canonico(primero))


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
