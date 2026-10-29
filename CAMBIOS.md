# Cambios

## 1. Respecto al código de ejemplo del módulo (`DL-NLP-M5-ExampleCode`)

| Ejemplo del módulo | Esta entrega | Por qué |
|---|---|---|
| `dominio.py`: `consultar`, `wer`, `medir`, `referencia`, `validar_resultado` sobre `datos.json` (demo:A, demo:B) | `dominio.py` + `herramientas.py`: filas por idioma con metadatos (id, corpus, versión, idioma, partición, normalización, referencia), catálogo con el sistema D **sin resultados**, validación de conteos, comparabilidad, WER exacto con `Fraction`, regla de decisión con abstención y orden de comprobaciones fijo | el enunciado exige idioma, procedencia, ausencia ≠ cero y abstención |
| Tool `calcular_wer(s, d, i, n)` | **eliminada**: el WER se calcula dentro de `obtener_resultados` | evita que el modelo copie cuatro conteos para calcularlo; justificación en la memoria |
| Errores como excepciones | errores previsibles como **datos** (`error.codigo`, `corregible`); fallos de transporte siguen siendo excepciones | idéntico comportamiento en las tres configuraciones y fallos distinguibles |
| `Resultado` (contrato único) | unión discriminada `Comparacion` / `DatosInsuficientes` (`estado`), `extra="forbid"`, validadores por motivo | una abstención no puede llevar WER ni ganador |
| — | `verificador.py`: recalcula cifras, fuentes, decisión y justificación de la abstención desde los datos | validez estructural ≠ coherencia con la evidencia |
| `smol_demo.py` | `agentes/smol_agente.py`: `ToolCallingAgent`, herramientas con el mismo contrato, `final_answer_checks` | decisión ToolCalling vs CodeAgent documentada |
| `pydantic_demo.py` | `agentes/pydantic_local.py`: `deps_type`, `output_type` (unión), `UsageLimits`, `output_validator` opcional | |
| `servidor_mcp.py` con `FastMCP` | `servidor_mcp.py` con `MCPServer` (`mcp.server.mcpserver`) + resource `asr://politica-evaluacion` + prompt `comparar_por_idioma`; control de acceso y auditoría en el servidor | `mcp.server.fastmcp` ya no existe en `mcp 2.x` |
| `pydantic_mcp.py` | `agentes/pydantic_mcp.py`: `MCPToolset` + `StdioTransport`, lectura del resource, reintentos acotados de transporte | `result.usage` es un atributo (no se llama) en pydantic-ai 2.x |
| — | `evaluacion/`: casos congelados con SHA-256, ejecutor, métricas, resumen; `pruebas/`; `datos/generar_escenarios.py` | |

## 2. Entre versiones de esta entrega (cada una con su resultado en `resultados/`)

* **v1** (`git tag v1-base`) → `resultados/base`. Primera versión evaluada con el modelo real.
* **v2** (`git tag v2`) → `v2_base`, `v2_prompted`, `v2_verificada`. Motivada por los fallos de `base`:
  * herramienta: el campo `estado` pasa a `disponibilidad` (colisionaba con el discriminador `estado` del contrato);
  * contrato: cada motivo de abstención exige los campos que la hacen comprobable;
  * descripciones y argumentos de las herramientas unificados en las tres configuraciones;
  * `UnexpectedModelBehavior` ya no se clasifica como fallo de infraestructura; un rechazo del servidor a una llamada mal formada es un reintento del modelo;
  * nueva opción `--salida prompted` (JSON en texto validado con la misma unión) y nueva variante `verificada` (verificador dentro del bucle).
* **v3** (`git tag v3`) → `v3_verificada`. **Modificación derivada de un fallo concreto** (C07, C07b, C04 en `v2_verificada`):
  el error del contrato enumera todos los campos que faltan a la vez y el verificador sugiere la abstención correcta.
* **Corrección de una métrica** (`evaluacion/corregir_reintentos.py`): el contador de reintentos no veía los de la salida en
  modo `prompted`; se reconstruyen desde la traza. Las tandas afectadas conservan el original en `medidas_sin_corregir.csv`.
* **Corrección de otra métrica** (`evaluacion/corregir_estructural.py`): las salidas válidas en forma pero rechazadas por el verificador se registraban como
  estructuralmente inválidas; ahora cuentan como válidas e incoherentes (el ejecutor ya lo hace bien: `evaluar_aceptacion(..., salida_descartada=...)`).
