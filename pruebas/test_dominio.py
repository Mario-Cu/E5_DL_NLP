from fractions import Fraction

import pytest

from asr_asistente.dominio import (AccesoDenegado, Permisos, Repositorio, Solicitud, decidir, diferencias_comparabilidad,
                                   problemas_conteos, wer, wer_fraccion)
from pruebas.ayudas import escenario


def test_wer_valores_del_enunciado():
    assert wer(8, 2, 1, 100) == pytest.approx(0.11)
    assert wer(5, 3, 1, 100) == pytest.approx(0.09)
    assert wer(0, 0, 150, 100) == pytest.approx(1.5)      # WER > 1 es válido
    assert wer(4, 1, 1, 100) == pytest.approx(0.06)
    assert wer(3, 2, 1, 100) == pytest.approx(0.06)


def test_wer_exacto_con_fracciones():
    assert wer_fraccion(1, 0, 0, 3) == Fraction(1, 3)
    assert wer_fraccion(4, 1, 1, 100) == wer_fraccion(3, 2, 1, 100)


@pytest.mark.parametrize("conteos", [(0, 0, 0, 0), (1, 0, 0, -5), (-1, 0, 0, 10), (99, 5, 0, 100),
                                     (1.5, 0, 0, 10), ("3", 0, 0, 10), (True, 0, 0, 10)])
def test_conteos_invalidos(conteos):
    assert problemas_conteos(*conteos)
    with pytest.raises(ValueError):
        wer_fraccion(*conteos)


def test_datos_tal_como_pide_el_enunciado(repo):
    assert repo.sistemas == ["A", "B", "C", "D"]
    assert {(f.idioma, f.sistema) for f in repo.filas} == {("es", "A"), ("es", "B"), ("es", "C"), ("en", "A"), ("en", "B")}
    assert repo.fila("demo", "es", "D") is None and repo.fila("demo", "en", "D") is None
    es = {f.referencia for f in repo.filas if f.idioma == "es"}
    en = {f.referencia for f in repo.filas if f.idioma == "en"}
    assert len(es) == 1 and len(en) == 1 and es != en       # misma referencia por idioma


def test_permisos():
    with pytest.raises(AccesoDenegado) as e:
        Permisos().comprobar_corpus("privado")
    assert e.value.codigo == "corpus_no_autorizado" and not e.value.corregible
    Permisos().comprobar_corpus("demo")


def decision(repo, idioma, sistemas, corpus="demo"):
    return decidir(repo, Permisos(), Solicitud(corpus, idioma, tuple(sistemas)))


def test_caso1_b_gana_es(repo):
    d = decision(repo, "es", "AB")
    assert (d.estado, d.resultado, d.ganador) == ("comparacion", "ganador", "B")


def test_caso2_empate_en(repo):
    d = decision(repo, "en", "AB")
    assert (d.estado, d.resultado, d.ganador) == ("comparacion", "empate", None)


def test_caso3_wer_mayor_que_uno_aceptado(repo):
    d = decision(repo, "es", "AC")
    assert d.estado == "comparacion" and d.ganador == "A"
    assert max(m.wer for m in d.medidas) == pytest.approx(1.5)


@pytest.mark.parametrize("idioma", ["es", "en"])
def test_caso4_sistema_d_sin_resultados(repo, idioma):
    d = decision(repo, idioma, "AD")
    assert (d.estado, d.motivo) == ("datos_insuficientes", "sistema_sin_resultados")
    assert d.ganador is None and not d.medidas


def test_caso5_idioma_sin_resultados(repo):
    d = decision(repo, "fr", "AB")
    assert d.motivo == "idioma_sin_resultados"


def test_caso6_sin_idioma(repo):
    d = decision(repo, None, "AB")
    assert d.motivo == "idioma_no_indicado" and d.pregunta_aclaracion


def test_caso7_no_comparables():
    r = escenario("incompatibles")
    assert decidir(r, Permisos(), Solicitud("demo", "es", ("A", "B"))).motivo == "filas_no_comparables"
    assert decidir(r, Permisos(), Solicitud("demo", "en", ("A", "B"))).motivo == "filas_no_comparables"
    assert "particion" in diferencias_comparabilidad(r.fila("demo", "es", "A"), r.fila("demo", "es", "B"))
    assert "normalizacion" in diferencias_comparabilidad(r.fila("demo", "en", "A"), r.fila("demo", "en", "B"))


def test_caso8_n_cero_y_conteos_invalidos():
    assert decidir(escenario("n_cero"), Permisos(), Solicitud("demo", "es", ("A", "B"))).motivo == "datos_invalidos"
    assert decidir(escenario("conteos_invalidos"), Permisos(), Solicitud("demo", "en", ("A", "B"))).motivo == "datos_invalidos"


def test_caso9_corpus_no_autorizado(repo):
    assert decision(repo, "es", "AB", corpus="privado").motivo == "acceso_denegado"


def test_caso10_inyeccion_no_cambia_la_decision():
    d = decidir(escenario("inyeccion"), Permisos(), Solicitud("demo", "es", ("A", "B")))
    assert (d.estado, d.ganador) == ("comparacion", "B")


def test_mismo_sistema_dos_veces(repo):
    assert decision(repo, "es", "AA").motivo == "sistemas_no_indicados"
