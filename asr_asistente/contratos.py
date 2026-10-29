"""Contrato de la respuesta final: unión discriminada ``comparacion`` / ``datos_insuficientes``.

Qué garantiza este módulo (**validez estructural**, solo eso):

* los campos obligatorios existen y tienen el tipo correcto (``strict``, ``extra="forbid"``);
* una abstención NO puede llevar WER, ganador ni medidas (el esquema no tiene esos campos);
* un empate no tiene ganador y un ganador debe ser uno de los dos sistemas comparados;
* hay al menos una fuente y ningún número negativo.

Lo que NO garantiza (y por eso existe ``verificador.py``): que la fila citada exista, que los
conteos coincidan con los datos, que el WER esté bien calculado, que el ganador sea el que dicen los
datos ni que la abstención esté justificada. Una salida puede ser válida y falsa.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .dominio import MOTIVOS, Decision

Motivo = Literal[
    "corpus_no_indicado", "idioma_no_indicado", "sistemas_no_indicados", "acceso_denegado",
    "idioma_sin_resultados", "sistema_sin_resultados", "datos_invalidos", "filas_no_comparables",
]
assert set(Motivo.__args__) == set(MOTIVOS)  # el contrato y el dominio no pueden divergir

#: motivos que piden información al usuario (la ejecución termina con una pregunta de aclaración)
MOTIVOS_ACLARACION = ("corpus_no_indicado", "idioma_no_indicado", "sistemas_no_indicados")


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MedidaSistema(_Estricto):
    """Cifras de un sistema, con la fila de datos que las respalda."""

    sistema: str = Field(min_length=1, description="Identificador del sistema, p. ej. 'A'.")
    fila: str = Field(min_length=1, description="Id de la fila de datos de la que salen las cifras, p. ej. 'demo:es:A'.")
    s: int = Field(ge=0)
    d: int = Field(ge=0)
    i: int = Field(ge=0)
    n: int = Field(gt=0)
    wer: float = Field(ge=0, description="(S+D+I)/N como razón; puede ser mayor que 1.")


class Comparacion(_Estricto):
    """Hay evidencia válida y comparable de los dos sistemas."""

    estado: Literal["comparacion"] = Field(
        description="Constante 'comparacion'. No confundir con el campo 'disponibilidad' de las herramientas.")
    corpus: str = Field(min_length=1)
    idioma: str = Field(min_length=2, max_length=2)
    medidas: list[MedidaSistema] = Field(min_length=2, max_length=2)
    resultado: Literal["ganador", "empate"]
    ganador: str | None = Field(description="Sistema con menor WER; null si hay empate.")
    fuentes: list[str] = Field(min_length=1, description="Ids de las filas consultadas.")
    limitaciones: str = Field(min_length=1, description="Alcance y límites de la comparación.")

    @model_validator(mode="after")
    def _coherencia_interna(self) -> "Comparacion":
        sistemas = [m.sistema for m in self.medidas]
        if len(set(sistemas)) != 2:
            raise ValueError("las dos medidas deben ser de sistemas distintos")
        if self.resultado == "empate" and self.ganador is not None:
            raise ValueError("un empate no puede tener ganador")
        if self.resultado == "ganador" and self.ganador not in sistemas:
            raise ValueError("el ganador debe ser uno de los dos sistemas comparados")
        return self


class DatosInsuficientes(_Estricto):
    """No hay evidencia suficiente o válida: se abstiene y dice cómo continuar."""

    estado: Literal["datos_insuficientes"] = Field(
        description="Constante 'datos_insuficientes'. El motivo concreto va en el campo 'motivo', no aquí.")
    motivo: Motivo = Field(description="Por qué no se puede comparar (uno de los valores permitidos).")
    corpus: str | None = None
    idioma: str | None = None
    sistemas: list[str] = Field(default_factory=list)
    faltante: list[str] = Field(default_factory=list, description="Qué falta (p. ej. ['resultados demo:es:D']).")
    detalle: str = Field(min_length=1, description="Explicación para el usuario, con base en la evidencia.")
    fuentes: list[str] = Field(default_factory=list, description="Filas consultadas (puede ser vacío).")
    pregunta_aclaracion: str | None = Field(
        default=None, description="Pregunta al usuario cuando falta un parámetro (corpus, idioma o sistemas).")

    @model_validator(mode="after")
    def _aclaracion(self) -> "DatosInsuficientes":
        if self.motivo in MOTIVOS_ACLARACION and not self.pregunta_aclaracion:
            raise ValueError("si falta un parámetro del usuario hay que formular una pregunta de aclaración")
        return self

    @model_validator(mode="after")
    def _campos_del_motivo(self) -> "DatosInsuficientes":
        """Cada motivo exige los campos que hacen la abstención comprobable contra los datos (contrato v2).

        Se añadió tras la evaluación base: varias abstenciones correctas no incluían corpus/idioma y el
        verificador no podía contrastarlas (``abstencion_sin_base``). En la v3 el error enumera TODOS los
        problemas a la vez: en la v2 se devolvían de uno en uno y el modelo agotaba los reintentos
        corrigiéndolos por turnos (y a veces borraba un campo bueno al añadir otro).
        """
        m, problemas = self.motivo, []
        if m == "corpus_no_indicado" and self.corpus is not None:
            problemas.append("`corpus` debe ser null (no se indicó corpus)")
        if m == "idioma_no_indicado" and self.idioma is not None:
            problemas.append("`idioma` debe ser null (no se indicó idioma)")
        if m == "acceso_denegado" and not self.corpus:
            problemas.append("falta `corpus` (el corpus no autorizado)")
        if m in ("idioma_sin_resultados", "sistema_sin_resultados", "datos_invalidos", "filas_no_comparables"):
            if not self.corpus:
                problemas.append("falta `corpus` (el consultado)")
            if not self.idioma:
                problemas.append("falta `idioma` (el consultado)")
        if m == "sistema_sin_resultados" and not self.sistemas:
            problemas.append("falta `sistemas` (lista de los sistemas pedidos)")
        if m in ("datos_invalidos", "filas_no_comparables") and not self.fuentes:
            problemas.append("falta `fuentes` (ids de las filas implicadas)")
        if problemas:
            raise ValueError(f"motivo {m}: " + "; ".join(problemas) +
                             ". Reenvía la respuesta COMPLETA manteniendo los campos que ya eran correctos")
        return self


#: Unión discriminada por ``estado``: es el ``output_type`` de Pydantic AI y el esquema de smolagents.
SalidaAsistente = Annotated[Union[Comparacion, DatosInsuficientes], Field(discriminator="estado")]
ADAPTADOR_SALIDA: TypeAdapter = TypeAdapter(SalidaAsistente)


def esquema_compacto() -> str:
    """JSON Schema de la unión discriminada en una línea (para pedir la salida como texto)."""
    import json
    return json.dumps(ADAPTADOR_SALIDA.json_schema(), ensure_ascii=False, separators=(",", ":"))


def validar_salida(valor) -> Comparacion | DatosInsuficientes:
    """Valida un dict o un texto JSON contra la unión discriminada (levanta ``ValidationError``)."""
    if isinstance(valor, (str, bytes)):
        return ADAPTADOR_SALIDA.validate_json(valor)
    if isinstance(valor, (Comparacion, DatosInsuficientes)):
        return valor
    return ADAPTADOR_SALIDA.validate_python(valor)


def desde_decision(dec: Decision, filas: dict[str, tuple[int, int, int, int]] | None = None) -> Comparacion | DatosInsuficientes:
    """Convierte la decisión de la referencia determinista al contrato.

    ``filas`` mapea id de fila → (s, d, i, n); se necesita solo para construir una ``Comparacion``.
    """
    if dec.estado == "datos_insuficientes":
        return DatosInsuficientes(
            estado="datos_insuficientes", motivo=dec.motivo, corpus=dec.corpus, idioma=dec.idioma,
            sistemas=list(dec.sistemas), faltante=list(dec.faltante), detalle=dec.detalle,
            fuentes=list(dec.fuentes), pregunta_aclaracion=dec.pregunta_aclaracion)
    assert filas is not None, "se necesitan los conteos para construir una comparación"
    medidas = []
    for m in dec.medidas:
        s, d, i, n = filas[m.fila]
        medidas.append(MedidaSistema(sistema=m.sistema, fila=m.fila, s=s, d=d, i=i, n=n, wer=m.wer))
    return Comparacion(estado="comparacion", corpus=dec.corpus, idioma=dec.idioma, medidas=medidas,
                       resultado=dec.resultado, ganador=dec.ganador, fuentes=list(dec.fuentes),
                       limitaciones=dec.detalle)
