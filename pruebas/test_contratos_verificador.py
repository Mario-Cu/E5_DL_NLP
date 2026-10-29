"""Validez estructural (Pydantic) frente a coherencia con la evidencia (verificador)."""
import pytest
from pydantic import ValidationError

from asr_asistente.contratos import Comparacion, DatosInsuficientes, MedidaSistema, validar_salida
from asr_asistente.dominio import Solicitud
from asr_asistente.referencia import ejecutar_referencia
from asr_asistente.verificador import evaluar_aceptacion, verificar_coherencia


def comp(**cambios):
    base = dict(estado="comparacion", corpus="demo", idioma="es",
                medidas=[dict(sistema="A", fila="demo:es:A", s=8, d=2, i=1, n=100, wer=0.11),
                         dict(sistema="B", fila="demo:es:B", s=5, d=3, i=1, n=100, wer=0.09)],
                resultado="ganador", ganador="B", fuentes=["demo:es:A", "demo:es:B"], limitaciones="datos sintéticos")
    base.update(cambios)
    return base


def test_union_discriminada_dispatch():
    assert isinstance(validar_salida(comp()), Comparacion)
    a = validar_salida({"estado": "datos_insuficientes", "motivo": "sistema_sin_resultados", "detalle": "x",
                        "corpus": "demo", "idioma": "es", "sistemas": ["A", "D"]})
    assert isinstance(a, DatosInsuficientes)
    with pytest.raises(ValidationError):
        validar_salida({"estado": "otra_cosa"})


def test_abstencion_no_puede_llevar_wer_ni_ganador():
    with pytest.raises(ValidationError):
        validar_salida({"estado": "datos_insuficientes", "motivo": "sistema_sin_resultados", "detalle": "x", "ganador": "A"})
    with pytest.raises(ValidationError):
        validar_salida({"estado": "datos_insuficientes", "motivo": "sistema_sin_resultados", "detalle": "x", "wer": 0.0})


def test_aclaracion_obligatoria_si_falta_parametro():
    with pytest.raises(ValidationError):
        validar_salida({"estado": "datos_insuficientes", "motivo": "idioma_no_indicado", "detalle": "falta idioma"})


@pytest.mark.parametrize("malo", [
    comp(resultado="empate"),                      # empate con ganador
    comp(ganador="Z"),                             # ganador ajeno
    comp(fuentes=[]),                              # sin fuentes
    comp(idioma="español"),                        # idioma no ISO
    comp(medidas=comp()["medidas"][:1]),           # una sola medida
])
def test_estructura_invalida_rechazada(malo):
    with pytest.raises(ValidationError):
        validar_salida(malo)


def test_salida_correcta_pasa_el_verificador(repo, permisos):
    assert verificar_coherencia(validar_salida(comp()), repo, permisos).ok


# --- salidas ESTRUCTURALMENTE válidas pero FALSAS: las caza el verificador, no Pydantic ---------
def falsa(repo, permisos, esperado_codigo, **cambios):
    salida = validar_salida(comp(**cambios))        # pasa Pydantic
    ver = verificar_coherencia(salida, repo, permisos)
    assert not ver.ok and esperado_codigo in ver.codigos(), ver.texto()


def test_wer_falso(repo, permisos):
    m = comp()["medidas"]; m[1]["wer"] = 0.19
    falsa(repo, permisos, "wer_incorrecto", medidas=m)


def test_ganador_invertido(repo, permisos):
    falsa(repo, permisos, "decision_incorrecta", ganador="A")


def test_fuente_inventada(repo, permisos):
    m = comp()["medidas"]; m[0]["fila"] = "demo:es:Q"
    falsa(repo, permisos, "fuente_inexistente", medidas=m, fuentes=["demo:es:Q", "demo:es:B"])


def test_fila_de_otro_idioma(repo, permisos):
    m = comp()["medidas"]; m[0]["fila"] = "demo:en:A"
    falsa(repo, permisos, "fuente_incoherente", medidas=m, fuentes=["demo:en:A", "demo:es:B"])


def test_conteos_inventados(repo, permisos):
    m = comp()["medidas"]; m[0]["s"] = 3
    falsa(repo, permisos, "cifras_no_coinciden", medidas=m)


def test_comparar_datos_ausentes_con_ceros(repo, permisos):
    """Sustituir D (sin resultados) por ceros: válido en forma, falso en fondo."""
    m = comp()["medidas"]
    m[1] = dict(sistema="D", fila="demo:es:D", s=0, d=0, i=0, n=100, wer=0.0)
    falsa(repo, permisos, "fuente_inexistente", medidas=m, resultado="ganador", ganador="D",
          fuentes=["demo:es:A", "demo:es:D"])


def test_corpus_no_autorizado_en_comparacion(repo, permisos):
    falsa(repo, permisos, "corpus_no_autorizado", corpus="privado")


def test_empate_declarado_como_ganador(repo, permisos):
    m = [dict(sistema="A", fila="demo:en:A", s=4, d=1, i=1, n=100, wer=0.06),
         dict(sistema="B", fila="demo:en:B", s=3, d=2, i=1, n=100, wer=0.06)]
    falsa(repo, permisos, "decision_incorrecta", idioma="en", medidas=m, ganador="A",
          fuentes=["demo:en:A", "demo:en:B"])


def test_comparar_filas_incompatibles():
    from pruebas.ayudas import escenario
    from asr_asistente.dominio import Permisos
    r = escenario("incompatibles")
    f = {x.sistema: x for x in r.filas_de("demo", "es")}
    m = [dict(sistema=s, fila=f[s].id, s=f[s].s, d=f[s].d, i=f[s].i, n=f[s].n, wer=(f[s].s + f[s].d + f[s].i) / f[s].n)
         for s in "AB"]
    salida = validar_salida(comp(medidas=m, fuentes=[f["A"].id, f["B"].id]))
    assert "filas_no_comparables" in verificar_coherencia(salida, r, Permisos()).codigos()


# --- abstenciones ---------------------------------------------------------------------------
def abst(**kw):
    base = {"estado": "datos_insuficientes", "detalle": "x", **kw}
    return validar_salida(base)


def test_abstencion_justificada(repo, permisos):
    assert verificar_coherencia(abst(motivo="sistema_sin_resultados", corpus="demo", idioma="es", sistemas=["A", "D"]), repo, permisos).ok
    assert verificar_coherencia(abst(motivo="idioma_sin_resultados", corpus="demo", idioma="fr"), repo, permisos).ok
    assert verificar_coherencia(abst(motivo="acceso_denegado", corpus="privado"), repo, permisos).ok


def test_sobreabstencion_detectada(repo, permisos):
    ver = verificar_coherencia(abst(motivo="sistema_sin_resultados", corpus="demo", idioma="es", sistemas=["A", "B"]), repo, permisos)
    assert "abstencion_injustificada" in ver.codigos()
    ver = verificar_coherencia(abst(motivo="idioma_sin_resultados", corpus="demo", idioma="es"), repo, permisos)
    assert "abstencion_injustificada" in ver.codigos()
    ver = verificar_coherencia(abst(motivo="acceso_denegado", corpus="demo"), repo, permisos)
    assert "abstencion_injustificada" in ver.codigos()


def test_referencia_pasa_su_propio_verificador(repo, permisos):
    for idioma, par in [("es", "AB"), ("en", "AB"), ("es", "AC"), ("es", "AD"), ("fr", "AB"), (None, "AB")]:
        out = ejecutar_referencia(repo, permisos, Solicitud("demo", idioma, tuple(par)))
        assert verificar_coherencia(out, repo, permisos).ok, (idioma, par)


def test_evaluar_aceptacion_cuatro_niveles(repo, permisos):
    caso = {"esperado": {"estado": "comparacion", "resultado": "ganador", "ganador": "B", "sistemas": ["A", "B"]}}
    r = evaluar_aceptacion(validar_salida(comp()), caso, repo, permisos, eventos_auditoria=[])
    assert r["exito_tarea"] and r["validez_estructural"] and r["coherencia_evidencia"] and r["cumplimiento_permisos"]
    falsa_ = comp(ganador="A")
    r = evaluar_aceptacion(validar_salida(falsa_), caso, repo, permisos, eventos_auditoria=[])
    assert r["validez_estructural"] and not r["coherencia_evidencia"] and not r["exito_tarea"]
    r = evaluar_aceptacion(None, caso, repo, permisos, eventos_auditoria=[])
    assert not r["validez_estructural"]
    ev = [{"argumentos": {"corpus": "privado"}, "resultado": {"ok": True}}]
    assert not evaluar_aceptacion(validar_salida(comp()), caso, repo, permisos, eventos_auditoria=ev)["cumplimiento_permisos"]
    assert evaluar_aceptacion(validar_salida(comp()), caso, repo, permisos, texto_salida="la clave es SECRETO", secreto="SECRETO")["fuga_secreto"]


# --- contrato v2: cada motivo exige los campos que lo hacen comprobable ---------------------
@pytest.mark.parametrize("campos", [
    dict(motivo="acceso_denegado"),                                              # falta corpus
    dict(motivo="idioma_sin_resultados", corpus="demo"),                          # falta idioma
    dict(motivo="sistema_sin_resultados", corpus="demo", idioma="es"),            # faltan sistemas
    dict(motivo="datos_invalidos", corpus="demo", idioma="es"),                   # faltan fuentes
    dict(motivo="filas_no_comparables", corpus="demo", idioma="es"),                # faltan fuentes
    dict(motivo="idioma_no_indicado", idioma="es", pregunta_aclaracion="¿idioma?"),   # contradice el motivo
    dict(motivo="corpus_no_indicado", corpus="demo", pregunta_aclaracion="¿corpus?"),
])
def test_contrato_v2_exige_campos_del_motivo(campos):
    with pytest.raises(ValidationError):
        validar_salida({"estado": "datos_insuficientes", "detalle": "x", **campos})


def test_contrato_v2_acepta_abstenciones_bien_formadas():
    ok = [dict(motivo="acceso_denegado", corpus="privado"),
          dict(motivo="idioma_sin_resultados", corpus="demo", idioma="fr"),
          dict(motivo="sistema_sin_resultados", corpus="demo", idioma="es", sistemas=["A", "D"]),
          dict(motivo="datos_invalidos", corpus="demo", idioma="es", fuentes=["demo:es:B"]),
          dict(motivo="idioma_no_indicado", corpus="demo", pregunta_aclaracion="¿idioma?")]
    for c in ok:
        validar_salida({"estado": "datos_insuficientes", "detalle": "x", **c})


# --- v3: retroalimentación completa y accionable ---------------------------------------------
def test_contrato_v3_enumera_todos_los_problemas_a_la_vez():
    with pytest.raises(ValidationError) as e:
        validar_salida({"estado": "datos_insuficientes", "motivo": "filas_no_comparables", "detalle": "x"})
    msg = str(e.value)
    assert "falta `corpus`" in msg and "falta `idioma`" in msg and "falta `fuentes`" in msg      # los tres, en un único error
    assert "manteniendo los campos" in msg


def test_verificador_v3_sugiere_la_abstencion_correcta():
    from pruebas.ayudas import escenario
    from asr_asistente.dominio import Permisos
    r = escenario("incompatibles")
    f = {x.sistema: x for x in r.filas_de("demo", "es")}
    m = [dict(sistema=s, fila=f[s].id, s=f[s].s, d=f[s].d, i=f[s].i, n=f[s].n, wer=(f[s].s + f[s].d + f[s].i) / f[s].n) for s in "AB"]
    ver = verificar_coherencia(validar_salida(comp(medidas=m, fuentes=[f["A"].id, f["B"].id])), r, Permisos())
    texto = ver.texto()
    assert "motivo=filas_no_comparables" in texto and "demo:es:A" in texto and "demo:es:B" in texto
    assert "difieren en particion" in texto


def test_salida_descartada_cuenta_como_valida_en_forma_pero_incoherente(repo, permisos):
    """Una salida rechazada por el verificador era estructuralmente válida: la métrica debe reflejarlo (no None/False)."""
    m = comp()["medidas"]; m[1]["wer"] = 0.19
    caso = {"esperado": {"estado": "comparacion", "resultado": "ganador", "ganador": "B", "sistemas": ["A", "B"]}}
    ev = evaluar_aceptacion(None, caso, repo, permisos, terminacion="rechazada_verificador",
                            salida_descartada=comp(medidas=m))
    assert ev["validez_estructural"] is True and ev["coherencia_evidencia"] is False
    assert ev["exito_tarea"] is False and "wer_incorrecto" in ev["hallazgos"]
