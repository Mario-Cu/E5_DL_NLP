import pytest

from asr_asistente.herramientas import Auditoria, ServicioResultados
from asr_asistente.dominio import Permisos
from pruebas.ayudas import escenario


def test_listar_sistemas_es(servicio):
    r = servicio.listar_sistemas("demo", "es")
    assert r.ok and r.idioma_con_datos
    disp = {s.sistema: s.disponible for s in r.sistemas}
    assert disp == {"A": True, "B": True, "C": True, "D": False}


def test_listar_idioma_sin_datos(servicio):
    r = servicio.listar_sistemas("demo", "fr")
    assert r.ok and not r.idioma_con_datos and not any(s.disponible for s in r.sistemas)


def test_obtener_resultados_disponible(servicio):
    r = servicio.obtener_resultados("demo", "es", "B")
    assert r.ok and r.disponibilidad == "disponible" and r.fila_id == "demo:es:B"
    assert r.fila.wer == pytest.approx(0.09) and r.fila.particion == "test"


def test_normalizacion_de_argumentos(servicio):
    r = servicio.obtener_resultados("demo", " ES ", " b ")
    assert r.disponibilidad == "disponible" and r.fila.sistema == "B" and r.fila.idioma == "es"


def test_sistema_ausente_no_es_cero(servicio):
    r = servicio.obtener_resultados("demo", "es", "D")
    assert r.ok and r.disponibilidad == "sin_resultados" and r.fila is None and "ceros" in r.detalle


def test_errores_previsibles_como_datos(servicio):
    assert servicio.obtener_resultados("demo", "español", "A").error.codigo == "idioma_invalido"
    e = servicio.obtener_resultados("demo", "es", "Z").error
    assert e.codigo == "sistema_desconocido" and e.corregible


def test_corpus_no_autorizado_denegado_y_auditado(servicio):
    r = servicio.obtener_resultados("privado", "es", "A")
    assert not r.ok and r.error.codigo == "corpus_no_autorizado" and not r.error.corregible
    assert r.fila is None
    ev = servicio.auditoria.eventos[-1]
    assert ev["argumentos"]["corpus"] == "privado" and ev["resultado"]["codigo_error"] == "corpus_no_autorizado"
    assert not servicio.listar_sistemas("privado", "es").ok


def test_datos_invalidos_sin_wer():
    s = ServicioResultados(escenario("n_cero"), Permisos(), Auditoria())
    r = s.obtener_resultados("demo", "es", "B")
    assert r.disponibilidad == "datos_invalidos" and r.fila is None and "N debe ser positivo" in r.detalle
    s = ServicioResultados(escenario("conteos_invalidos"), Permisos(), Auditoria())
    assert s.obtener_resultados("demo", "en", "B").disponibilidad == "datos_invalidos"


def test_comentario_externo_llega_como_dato():
    s = ServicioResultados(escenario("inyeccion"), Permisos(), Auditoria())
    r = s.obtener_resultados("demo", "es", "B")
    assert r.disponibilidad == "disponible" and "ignora" in r.fila.comentario_externo.lower()


def test_auditoria_jsonl(tmp_path, repo, permisos):
    ruta = tmp_path / "a.jsonl"
    s = ServicioResultados(repo, permisos, Auditoria(ruta, origen="prueba"))
    s.obtener_resultados("demo", "es", "A"); s.obtener_resultados("privado", "es", "A")
    eventos = Auditoria.leer(ruta)
    assert len(eventos) == 2 and eventos[0]["origen"] == "prueba"
    assert eventos[1]["resultado"]["codigo_error"] == "corpus_no_autorizado"


def test_no_hay_superficie_peligrosa():
    import inspect
    nombres = {n for n, _ in inspect.getmembers(ServicioResultados, inspect.isfunction) if not n.startswith("_")}
    assert nombres == {"listar_sistemas", "obtener_resultados"}


def test_control_de_acceso_protege_el_secreto_canario():
    from asr_asistente.politica import SECRETO_CANARIO
    repo = escenario("con_privado")
    # control negativo: SIN restricción el dato reservado sí sería accesible (el detector de fugas tiene sentido)
    abierto = ServicioResultados(repo, Permisos(frozenset({"demo", "privado"})), Auditoria())
    assert SECRETO_CANARIO in abierto.obtener_resultados("privado", "es", "A").model_dump_json()
    # con la política real (solo 'demo'), el secreto no sale por ninguna vía
    cerrado = ServicioResultados(repo, Permisos(), Auditoria())
    salidas = [cerrado.obtener_resultados("privado", "es", "A"), cerrado.listar_sistemas("privado", "es"),
               cerrado.obtener_resultados("demo", "es", "A"), cerrado.listar_sistemas("demo", "es")]
    assert all(SECRETO_CANARIO not in s.model_dump_json() for s in salidas)
