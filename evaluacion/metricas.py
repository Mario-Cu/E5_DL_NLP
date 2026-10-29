"""Los cuatro niveles de la evaluación (criterios citados en ``casos.json``).

La lógica vive en ``asr_asistente.verificador`` (``evaluar_aceptacion``) para que la use también el verificador
dentro del bucle del agente; este módulo solo la expone con el nombre que cita ``casos.json``.
"""
from asr_asistente.verificador import evaluar_aceptacion, verificar_coherencia  # noqa: F401
