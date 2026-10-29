"""Núcleo determinista del asistente de comparación ASR.

No importa ningún framework de agentes: smolagents, Pydantic AI y MCP solo son
adaptadores sobre este módulo. Contiene:

* la lectura de datos (``Repositorio``) y su procedencia;
* la validación de filas y la fórmula de WER (aritmética exacta con fracciones);
* las reglas de acceso (corpus autorizados);
* la regla de comparación (``decidir``), que es la *referencia determinista*:
  recibe parámetros explícitos y no interpreta lenguaje natural.

Cambios respecto al código del módulo (``dominio.py`` de ejemplo): filas por
idioma con metadatos, catálogo con sistemas sin resultados, comparabilidad,
errores tipados y decisión con abstención.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
DATOS_POR_DEFECTO = RAIZ / "datos" / "resultados_asr.json"

# Campos que deben coincidir para considerar dos filas comparables.
CAMPOS_COMPARABILIDAD = ("corpus", "version", "idioma", "particion", "normalizacion", "referencia")

RE_IDIOMA = re.compile(r"^[a-z]{2}$")


# --------------------------------------------------------------------------- #
# Errores de dominio (distintos de los errores de transporte o de infraestructura)
# --------------------------------------------------------------------------- #
class ErrorDominio(Exception):
    """Error previsible. ``corregible`` indica si el modelo puede arreglarlo cambiando argumentos."""

    def __init__(self, codigo: str, mensaje: str, corregible: bool = True):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.corregible = corregible


class ArgumentoInvalido(ErrorDominio):
    def __init__(self, codigo: str, mensaje: str):
        super().__init__(codigo, mensaje, corregible=True)


class AccesoDenegado(ErrorDominio):
    """Violación de permisos: no se reintenta cambiando argumentos ni se oculta."""

    def __init__(self, mensaje: str):
        super().__init__("corpus_no_autorizado", mensaje, corregible=False)


class ErrorInfraestructura(Exception):
    """Fichero de datos ausente o corrupto: no es un resultado de negocio."""


# --------------------------------------------------------------------------- #
# Datos
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FilaCruda:
    """Fila tal como viene en el fichero; los conteos pueden ser inválidos (no se asume nada)."""

    id: str
    corpus: str
    version: str
    idioma: str
    sistema: str
    particion: str
    normalizacion: str
    referencia: str
    s: Any
    d: Any
    i: Any
    n: Any
    comentario_externo: str | None = None
    procedencia: str = ""


def _es_entero(x: Any) -> bool:
    return type(x) is int  # excluye bool, float y str


def problemas_conteos(s: Any, d: Any, i: Any, n: Any) -> list[str]:
    """Lista de motivos por los que unos conteos no son válidos (vacía si lo son)."""
    problemas: list[str] = []
    for nombre, valor in (("S", s), ("D", d), ("I", i), ("N", n)):
        if not _es_entero(valor):
            problemas.append(f"{nombre} no es un entero ({valor!r})")
    if problemas:
        return problemas
    for nombre, valor in (("S", s), ("D", d), ("I", i)):
        if valor < 0:
            problemas.append(f"{nombre} es negativo ({valor})")
    if n <= 0:
        problemas.append(f"N debe ser positivo (N={n})")
    if not problemas and s + d > n:
        problemas.append(f"S+D={s + d} supera N={n}")
    return problemas


def wer_fraccion(s: int, d: int, i: int, n: int) -> Fraction:
    """WER exacta (S+D+I)/N. Las inserciones no tienen cota: un WER > 1 es válido."""
    problemas = problemas_conteos(s, d, i, n)
    if problemas:
        raise ValueError("Conteos no válidos: " + "; ".join(problemas))
    return Fraction(s + d + i, n)


def wer(s: int, d: int, i: int, n: int) -> float:
    """WER como razón (no porcentaje). Función interna: el LLM no reimplementa la fórmula."""
    return float(wer_fraccion(s, d, i, n))


def problemas_fila(fila: FilaCruda) -> list[str]:
    return problemas_conteos(fila.s, fila.d, fila.i, fila.n)


class Repositorio:
    """Lectura de solo lectura de UN fichero de datos fijado por la aplicación.

    La ruta nunca la elige el modelo: llega por configuración del programa/servidor.
    """

    def __init__(self, ruta: str | Path | None = None):
        self.ruta = Path(ruta) if ruta else DATOS_POR_DEFECTO
        try:
            bruto = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ErrorInfraestructura(f"No se pudo leer el fichero de datos: {exc}") from exc
        try:
            self.version_datos: str = bruto["version_datos"]
            self.corpus_info: dict[str, dict] = bruto["corpus"]
            self.sistemas: list[str] = [s["id"] for s in bruto["sistemas"]]
            self.filas: list[FilaCruda] = [FilaCruda(**f) for f in bruto["filas"]]
        except (KeyError, TypeError) as exc:
            raise ErrorInfraestructura(f"Esquema de datos incorrecto: {exc}") from exc
        ids = [f.id for f in self.filas]
        if len(ids) != len(set(ids)):
            raise ErrorInfraestructura("Identificadores de fila duplicados")

    # -- consultas internas (la autorización se comprueba en el servicio, no aquí) --
    def fila(self, corpus: str, idioma: str, sistema: str) -> FilaCruda | None:
        for f in self.filas:
            if (f.corpus, f.idioma, f.sistema) == (corpus, idioma, sistema):
                return f
        return None

    def filas_de(self, corpus: str, idioma: str) -> list[FilaCruda]:
        return [f for f in self.filas if f.corpus == corpus and f.idioma == idioma]

    def idiomas(self, corpus: str) -> list[str]:
        return sorted({f.idioma for f in self.filas if f.corpus == corpus})

    def fila_por_id(self, fila_id: str) -> FilaCruda | None:
        return next((f for f in self.filas if f.id == fila_id), None)


@dataclass(frozen=True)
class Permisos:
    """Autoridad impuesta por el programa. Nada de esto se genera ni se negocia con el modelo."""

    corpus_autorizados: frozenset[str] = frozenset({"demo"})

    def comprobar_corpus(self, corpus: str) -> None:
        if corpus not in self.corpus_autorizados:
            raise AccesoDenegado(
                f"Acceso denegado al corpus {corpus!r}: solo se permite "
                f"{sorted(self.corpus_autorizados)}.")


def normalizar_idioma(idioma: str) -> str:
    if not isinstance(idioma, str):
        raise ArgumentoInvalido("idioma_invalido", "El idioma debe ser texto (código ISO 639-1, p. ej. 'es').")
    valor = idioma.strip().lower()
    if not RE_IDIOMA.match(valor):
        raise ArgumentoInvalido(
            "idioma_invalido",
            f"Idioma {idioma!r} no válido: use un código ISO 639-1 de dos letras, p. ej. 'es' o 'en'.")
    return valor


def normalizar_sistema(sistema: str, repo: Repositorio) -> str:
    if not isinstance(sistema, str):
        raise ArgumentoInvalido("sistema_desconocido", "El sistema debe ser texto (p. ej. 'A').")
    valor = sistema.strip().upper()
    if valor not in repo.sistemas:
        raise ArgumentoInvalido(
            "sistema_desconocido",
            f"Sistema {sistema!r} fuera del catálogo; sistemas conocidos: {repo.sistemas}.")
    return valor


# --------------------------------------------------------------------------- #
# Regla de comparación (referencia determinista)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Solicitud:
    """Parámetros explícitos de un caso. La referencia no atribuye comprensión de lenguaje natural."""

    corpus: str | None
    idioma: str | None
    sistemas: tuple[str, ...]


@dataclass(frozen=True)
class MedidaWer:
    sistema: str
    fila: str
    errores: int  # S+D+I
    n: int

    @property
    def fraccion(self) -> Fraction:
        return Fraction(self.errores, self.n)

    @property
    def wer(self) -> float:
        return float(self.fraccion)


@dataclass(frozen=True)
class Decision:
    estado: str  # 'comparacion' | 'datos_insuficientes'
    corpus: str | None = None
    idioma: str | None = None
    sistemas: tuple[str, ...] = ()
    medidas: tuple[MedidaWer, ...] = ()
    resultado: str | None = None  # 'ganador' | 'empate'
    ganador: str | None = None
    motivo: str | None = None
    faltante: tuple[str, ...] = ()
    detalle: str = ""
    fuentes: tuple[str, ...] = ()
    pregunta_aclaracion: str | None = None


MOTIVOS = (
    "corpus_no_indicado", "idioma_no_indicado", "sistemas_no_indicados", "acceso_denegado",
    "idioma_sin_resultados", "sistema_sin_resultados", "datos_invalidos", "filas_no_comparables",
)


def limitaciones_base(corpus: str, idioma: str) -> str:
    return (f"Datos sintéticos y agregados del corpus {corpus} (idioma {idioma}, una sola partición y "
            "una sola normalización). No hay intervalos de confianza ni se afirma significación "
            "estadística; no permite generalizar a otros idiomas, corpus o condiciones, ni extraer "
            "conclusiones clínicas.")


def _insuficiente(motivo: str, solicitud: Solicitud, detalle: str, faltante=(), fuentes=(), pregunta=None) -> Decision:
    return Decision(estado="datos_insuficientes", corpus=solicitud.corpus, idioma=solicitud.idioma,
                    sistemas=tuple(solicitud.sistemas), motivo=motivo, faltante=tuple(faltante),
                    detalle=detalle, fuentes=tuple(fuentes), pregunta_aclaracion=pregunta)


def diferencias_comparabilidad(a: FilaCruda, b: FilaCruda) -> list[str]:
    """Campos de metadatos que impiden comparar. Mismo N no basta; con la misma referencia N debe coincidir."""
    dif = [c for c in CAMPOS_COMPARABILIDAD if getattr(a, c) != getattr(b, c)]
    if a.referencia == b.referencia and a.n != b.n:
        dif.append("n (misma referencia con distinto N)")
    return dif


def decidir(repo: Repositorio, permisos: Permisos, solicitud: Solicitud) -> Decision:
    """Regla de comparación con abstención. Orden de comprobaciones fijado y documentado."""
    if not solicitud.corpus:
        return _insuficiente("corpus_no_indicado", solicitud, "No se indicó el corpus.",
                             ["corpus"], pregunta="¿En qué corpus quieres comparar?")
    if not solicitud.idioma:
        return _insuficiente("idioma_no_indicado", solicitud,
                             "No se indicó el idioma y los resultados dependen de él.",
                             ["idioma"], pregunta="¿En qué idioma quieres comparar los sistemas?")
    if len(set(solicitud.sistemas)) != 2:
        return _insuficiente("sistemas_no_indicados", solicitud,
                             "Se necesitan exactamente dos sistemas distintos para comparar.",
                             ["sistemas"], pregunta="¿Qué dos sistemas quieres comparar?")
    try:
        permisos.comprobar_corpus(solicitud.corpus)
    except AccesoDenegado as exc:
        return _insuficiente("acceso_denegado", solicitud, exc.mensaje, ["corpus autorizado"])

    corpus, idioma = solicitud.corpus, solicitud.idioma
    if not repo.filas_de(corpus, idioma):
        return _insuficiente("idioma_sin_resultados", solicitud,
                             f"No hay resultados de ningún sistema en el corpus {corpus} para el idioma {idioma}.",
                             [f"resultados {corpus}/{idioma}"])

    filas: list[FilaCruda] = []
    sin_resultados: list[str] = []
    for sistema in solicitud.sistemas:
        f = repo.fila(corpus, idioma, sistema)
        if f is None:
            sin_resultados.append(sistema)
        else:
            filas.append(f)
    consultadas = tuple(f.id for f in filas)
    if sin_resultados:
        return _insuficiente(
            "sistema_sin_resultados", solicitud,
            f"No hay resultados disponibles para {', '.join(sin_resultados)} en {corpus}/{idioma}; "
            "no se sustituyen por ceros.", [f"{corpus}:{idioma}:{s}" for s in sin_resultados], consultadas)

    for f in filas:
        problemas = problemas_fila(f)
        if problemas:
            return _insuficiente("datos_invalidos", solicitud,
                                 f"La fila {f.id} tiene conteos inválidos: " + "; ".join(problemas) + ".",
                                 [f"conteos válidos de {f.id}"], consultadas)

    dif = diferencias_comparabilidad(filas[0], filas[1])
    if dif:
        return _insuficiente("filas_no_comparables", solicitud,
                             f"Las filas {filas[0].id} y {filas[1].id} difieren en: {', '.join(dif)}; "
                             "la comparación no sería concluyente.", [], consultadas)

    medidas = tuple(MedidaWer(f.sistema, f.id, f.s + f.d + f.i, f.n) for f in filas)
    a, b = medidas
    if a.fraccion == b.fraccion:
        resultado, ganador = "empate", None
    else:
        resultado, ganador = "ganador", (a if a.fraccion < b.fraccion else b).sistema
    return Decision(estado="comparacion", corpus=corpus, idioma=idioma,
                    sistemas=tuple(m.sistema for m in medidas), medidas=medidas,
                    resultado=resultado, ganador=ganador, fuentes=consultadas,
                    detalle=limitaciones_base(corpus, idioma))
