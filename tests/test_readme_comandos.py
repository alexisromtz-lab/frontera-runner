"""El README es lo unico que un prospecto lee antes de instalar: aqui tiene lector.

Hasta hoy no lo tenia. El 28-Nov-2026 este archivo mandaba `uvx --from frontera-runner==0.2.2` y el
indice respondia `versiones: ['0.2.0']`: el comando publicado no resolvia en ningun lado, y nada lo
noto porque ninguna prueba leia el README.

Dos capas, a proposito:

* **Offline, en cada corrida.** Toda etiqueta, todo wheel y todo ejecutable citados se cotejan
  contra `pyproject.toml`, contra `frontera_runner.__version__` y contra las etiquetas del
  repositorio. Y ninguna invocacion que resuelva por el indice se permite sin un ancla fechada
  —`<!-- INDICE: ... -->`— que declare que version se midio alli, cuando y donde.
* **Remota, opt-in.** Con `FRONTERA_VERIFICAR_EXTERNO=1` se re-verifica el ancla contra GitHub
  Releases y contra `pypi.org`. No corre por defecto: un test con HTTP en cada corrida cambia de
  veredicto fuera del arbol y enrojece en un `env -i` sin red, que es justo el entorno en el que
  este paquete se mide.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib
import unittest
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import frontera_runner  # noqa: E402

# El ancla que convierte una promesa de indice en una medicion fechada.
ANCLA = re.compile(
    r"<!--\s*INDICE:\s*(?P<nombre>[A-Za-z0-9._-]+)\s*"
    r"·\s*publicado\s+(?P<version>\d+\.\d+\.\d+)\s*"
    r"·\s*medido\s+(?P<fecha>\d{4}-\d{2}-\d{2})\s*"
    r"·\s*(?P<url>https?://[^\s>]+)\s*-->"
)

# Una invocacion que resuelve por el indice: el nombre desnudo, sin `git+`, sin URL y sin ruta.
INDICE = re.compile(
    r"(?:pip3?\s+install|uv\s+pip\s+install|uv\s+add|uvx\s+--from)"
    r"\s+\"?(?P<requisito>frontera[-_]runner(?P<pin>==\d+\.\d+\.\d+)?)\"?"
)

ETIQUETA = re.compile(r"(?<![\w.])v(?P<version>\d+\.\d+\.\d+)(?![\w.])")

# Un nombre con guion que empieza como el paquete es un ejecutable, y los ejecutables los declara
# el manifiesto: `ceros-implicitos`, no `ceros-implicitos-lint`.
EJECUTABLE = re.compile(r"(?<![\w./-])(?P<nombre>(?:frontera|ceros)(?:-[a-z0-9]+)+)(?![\w/])")

WHEEL = re.compile(r"\S+\.whl")

WHEELS_DE_RELEASE = re.compile(
    r"https://github\.com/alexisromtz-lab/frontera-runner/releases/download/\S+?\.whl"
)

UNIDADES = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
DECENAS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def leer_readme():
    return (RAIZ / "README.md").read_text(encoding="utf-8")


def leer_manifiesto():
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    return datos["project"]


def linea_de(texto, posicion):
    return texto.count("\n", 0, posicion) + 1


def ancla_de_indice(texto):
    encontradas = list(ANCLA.finditer(texto))
    if len(encontradas) > 1:
        raise AssertionError(
            "el ancla de indice aparece %d veces en README.md: una sola, o ninguna"
            % len(encontradas)
        )
    return encontradas[0].groupdict() if encontradas else None


def violaciones_de_indice(texto):
    """Ninguna invocacion por indice sin ancla fechada, y la version citada es la del ancla."""
    ancla = ancla_de_indice(texto)
    problemas = []
    for hallado in INDICE.finditer(texto):
        linea = linea_de(texto, hallado.start())
        requisito = hallado.group("requisito")
        if ancla is None:
            problemas.append(
                "README.md:%d: `%s` resuelve por el indice y no hay ancla INDICE que diga que "
                "version se midio alli" % (linea, requisito)
            )
            continue
        if hallado.group("pin") is None:
            problemas.append(
                "README.md:%d: `%s` sin version: el indice no es un pin, y lo medido es %s"
                % (linea, requisito, ancla["version"])
            )
        elif hallado.group("pin") != "==" + ancla["version"]:
            problemas.append(
                "README.md:%d: cita `%s` y el ancla mide `%s` en el indice"
                % (linea, requisito, ancla["version"])
            )
    return problemas


def violaciones_de_version(texto, version, ejecutables):
    """Lo que el README cita es lo que el manifiesto declara, y el wheel es el nombre PEP 427."""
    problemas = []
    for hallado in ETIQUETA.finditer(texto):
        if hallado.group("version") != version:
            problemas.append(
                "README.md:%d: cita la etiqueta `v%s` y el manifiesto declara `%s`"
                % (linea_de(texto, hallado.start()), hallado.group("version"), version)
            )
    for hallado in EJECUTABLE.finditer(texto):
        nombre = hallado.group("nombre")
        if nombre not in ejecutables:
            problemas.append(
                "README.md:%d: `%s` no es un ejecutable del manifiesto (%s)"
                % (linea_de(texto, hallado.start()), nombre, ", ".join(sorted(ejecutables)) or "ninguno")
            )
    esperado = "frontera_runner-%s-py3-none-any.whl" % version
    for hallado in WHEEL.finditer(texto):
        citado = hallado.group(0).rsplit("/", 1)[-1]
        if citado != esperado:
            problemas.append(
                "README.md:%d: cita `%s` y el artefacto del manifiesto se llama `%s`"
                % (linea_de(texto, hallado.start()), citado, esperado)
            )
    citados = {hallado.group("nombre") for hallado in EJECUTABLE.finditer(texto)}
    for nombre in sorted(set(ejecutables) - citados):
        problemas.append(
            "README.md: el manifiesto instala `%s` y el README no lo menciona nunca" % nombre
        )
    return problemas


def seccion(texto, titulo):
    inicio = re.search(r"^##\s+%s\s*$" % re.escape(titulo), texto, re.M)
    if inicio is None:
        raise AssertionError("README.md no tiene la seccion `## %s`" % titulo)
    resto = texto[inicio.end() :]
    fin = re.search(r"^##\s+", resto, re.M)
    return resto[: fin.start()] if fin else resto


def numero(crudo):
    crudo = crudo.strip().lower()
    if crudo.isdigit():
        return int(crudo)
    decena, _, unidad = crudo.partition("-")
    if unidad:
        if decena not in DECENAS or unidad not in UNIDADES or UNIDADES[unidad] > 9:
            raise ValueError("numero no reconocido: %s" % crudo)
        return DECENAS[decena] + UNIDADES[unidad]
    if crudo in DECENAS:
        return DECENAS[crudo]
    if crudo in UNIDADES:
        return UNIDADES[crudo]
    raise ValueError("numero no reconocido: %s" % crudo)


def numero_declarado_en_tests(texto):
    hallado = re.search(r"\b([a-z]+(?:-[a-z]+)?|\d+)\s+tests\b", seccion(texto, "Tests"), re.I)
    if hallado is None:
        raise AssertionError("la seccion `## Tests` de README.md no publica un conteo de pruebas")
    return numero(hallado.group(1))


def casos_descubiertos():
    return unittest.defaultTestLoader.discover(str(RAIZ / "tests")).countTestCases()


class ElReadmeNoPrometeLoQueNoCorre(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = leer_readme()
        cls.manifiesto = leer_manifiesto()
        cls.ejecutables = set(cls.manifiesto.get("scripts", {}))

    def test_el_readme_de_hoy_pasa_las_tres_reglas(self):
        self.assertEqual(violaciones_de_indice(self.texto), [])
        self.assertEqual(
            violaciones_de_version(self.texto, self.manifiesto["version"], self.ejecutables), []
        )
        self.assertEqual(
            numero_declarado_en_tests(self.texto), casos_descubiertos()
        )

    def test_el_ancla_de_indice_es_una_medicion_fechada(self):
        ancla = ancla_de_indice(self.texto)
        if ancla is None:
            self.skipTest("NO_MEDIDO: README.md no cita el indice, no hay ancla que verificar")
        self.assertEqual(ancla["nombre"], self.manifiesto["name"])
        self.assertRegex(ancla["fecha"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("/pypi/%s/json" % self.manifiesto["name"], ancla["url"])

    def test_la_version_del_paquete_es_una_sola(self):
        self.assertEqual(
            frontera_runner.__version__,
            self.manifiesto["version"],
            "`frontera_runner/__init__.py` y `pyproject.toml` declaran versiones distintas",
        )

    def test_cada_etiqueta_citada_existe_en_el_repositorio(self):
        if not (RAIZ / ".git").exists():
            self.skipTest("NO_MEDIDO: no hay `.git` (sdist o export), la etiqueta no se resuelve")
        etiquetas = subprocess.run(
            ["git", "-C", str(RAIZ), "tag", "--list"], capture_output=True, text=True
        )
        if etiquetas.returncode != 0:
            self.skipTest("NO_MEDIDO: git no responde (%s)" % etiquetas.stderr.strip())
        if not etiquetas.stdout.strip():
            self.skipTest("NO_MEDIDO: este clon no trae etiquetas (clon superficial)")
        for version in sorted({m.group("version") for m in ETIQUETA.finditer(self.texto)}):
            resuelta = subprocess.run(
                ["git", "-C", str(RAIZ), "rev-parse", "--verify", "refs/tags/v%s^{commit}" % version],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                resuelta.returncode,
                0,
                "README.md cita la etiqueta `v%s` y el repositorio no la tiene: %s"
                % (version, resuelta.stderr.strip()),
            )

    def test_el_lector_muerde(self):
        """Un verde que nunca se pone rojo no ha mostrado que mide: cinco mutaciones, cinco rojos."""
        version = self.manifiesto["version"]
        bueno = self.texto
        # Cada mutacion se construye por insercion o por sustitucion medida, nunca por un literal
        # del README: si el texto cambia de redaccion, la mutacion sigue aplicandose.
        desfasada = "0.0.1" if version != "0.0.1" else "0.0.2"
        celda = "\n```bash\nuvx --from frontera-runner==%s ceros-implicitos .\n```\n" % version
        yaml_desfasado = (
            "\n```yaml\n"
            "      uses: alexisromtz-lab/frontera-runner/.github/workflows/"
            "reusable-ceros.yml@v%s\n"
            "```\n" % desfasada
        )
        wheel_mal_nombrado = (
            "\n```bash\nuvx --from https://example.invalid/frontera-runner-%s-py3-none-any.whl"
            " ceros-implicitos .\n```\n" % version
        )
        cuerpo_tests = seccion(bueno, "Tests")
        inflado = bueno.replace(
            cuerpo_tests,
            re.sub(
                r"\b([a-z]+(?:-[a-z]+)?|\d+)\s+tests\b",
                "%d tests" % (casos_descubiertos() + 1),
                cuerpo_tests,
                count=1,
                flags=re.I,
            ),
        )
        mutaciones = [
            (
                "invocacion por indice sin version",
                bueno + "\n```bash\npip install frontera-runner\n```\n",
                lambda t: violaciones_de_indice(t),
            ),
            (
                "invocacion por indice sin ancla",
                ANCLA.sub("", bueno) + celda,
                lambda t: violaciones_de_indice(t),
            ),
            (
                "etiqueta desfasada",
                bueno + yaml_desfasado,
                lambda t: violaciones_de_version(t, version, self.ejecutables),
            ),
            (
                "wheel que no es el nombre PEP 427",
                bueno + wheel_mal_nombrado,
                lambda t: violaciones_de_version(t, version, self.ejecutables),
            ),
            (
                "conteo de pruebas inflado",
                inflado,
                lambda t: [
                    "conteo"
                ]
                if numero_declarado_en_tests(t) != casos_descubiertos()
                else [],
            ),
        ]
        for nombre, mutado, lector in mutaciones:
            with self.subTest(mutacion=nombre):
                if mutado == bueno:
                    self.fail("la mutacion `%s` no cambio nada" % nombre)
                self.assertNotEqual(lector(mutado), [], "`%s` no puso rojo al lector" % nombre)


@unittest.skipUnless(
    os.environ.get("FRONTERA_VERIFICAR_EXTERNO") == "1",
    "NO_MEDIDO: sonda externa desactivada (FRONTERA_VERIFICAR_EXTERNO=1 la activa)",
)
class ElAnclaSigueSiendoVerdad(unittest.TestCase):
    """Re-verificacion del ancla: solo cuando alguien la pide, porque esto sale a la red."""

    @classmethod
    def setUpClass(cls):
        cls.texto = leer_readme()
        cls.manifiesto = leer_manifiesto()

    @staticmethod
    def traer(url):
        peticion = urllib.request.Request(
            url, headers={"User-Agent": "frontera-runner-readme-gate"}
        )
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return respuesta.status, respuesta.read()

    def test_el_indice_no_supero_el_ancla(self):
        ancla = ancla_de_indice(self.texto)
        self.assertIsNotNone(ancla, "README.md cita el indice sin ancla fechada")
        estado, cuerpo = self.traer(ancla["url"])
        self.assertEqual(estado, 200)
        datos = json.loads(cuerpo)
        servidas = sorted(datos.get("releases", {}))
        self.assertIn(
            ancla["version"],
            servidas,
            "el ancla dice que `%s` esta en el indice y el indice sirve %s"
            % (ancla["version"], servidas),
        )
        self.assertTrue(
            datos["releases"][ancla["version"]],
            "`%s` figura en el indice sin ningun artefacto" % ancla["version"],
        )
        techo = max(servidas, key=lambda v: tuple(int(x) for x in v.split(".")))
        self.assertEqual(
            techo,
            ancla["version"],
            "el ancla envejecio: el indice ya sirve `%s` y README.md sigue midiendo `%s`"
            % (techo, ancla["version"]),
        )

    def test_los_assets_citados_existen(self):
        urls = sorted(set(WHEELS_DE_RELEASE.findall(self.texto)))
        self.assertNotEqual(urls, [], "el README no cita ningun asset de Release")
        for url in urls:
            with self.subTest(asset=url):
                estado, cuerpo = self.traer(url)
                self.assertEqual(estado, 200)
                self.assertGreater(len(cuerpo), 0, "el asset %s responde vacio" % url)


if __name__ == "__main__":
    unittest.main()
