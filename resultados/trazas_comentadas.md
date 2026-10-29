# Trazas comentadas (ejecuciones reales con `qwen2.5:14b`)

Todas las trazas son de ejecuciones **reales** (Ollama en local, Windows 11, Python 3.13.5). Los ficheros completos están en
`resultados/<tanda>/trazas/<config>_<caso>_<repetición>.json`. Los números de tiempo, solicitudes y tokens salen de
`medidas.csv` de la misma tanda. Aquí solo se quita lo que no aporta (campos `null`, texto de procedencia repetido).

Leyenda: `req` = solicitudes al modelo; `tools` = llamadas a herramienta; `reint` = reintentos del modelo (salida inválida o
rechazo del verificador); `tok` = tokens de entrada/salida según Ollama.

---

## Traza 1 — Correcta: `pydantic_mcp`, caso C01 (A vs B en español), tanda `v3_verificada`

Resultado: `comparacion`, ganador **B**. 8,6 s · req 2 · tools 3 · reint 0 · tok 5518/279 · arranque del servidor MCP 1,3 s.

| # | Qué pasa | Comentario |
|---|---|---|
| 1 | El host (Pydantic AI) arranca el servidor MCP por stdio, negocia la revisión **2026-07-28**, lee el resource `asr://politica-evaluacion`, comprueba su hash y lo mete en las instrucciones. | La política viaja por MCP, pero el hash demuestra que es el mismo texto que usan las configuraciones locales. |
| 2 | El modelo pide **en paralelo** `listar_sistemas(demo, es)`, `obtener_resultados(demo, es, A)` y `obtener_resultados(demo, es, B)`. | Una sola solicitud al modelo para tres llamadas. El orden de los argumentos cambia entre llamadas: no importa, van por nombre. |
| 3 | `listar_sistemas` → A, B, C disponibles y **D `disponible=false`**. | Se ve que D existe en el catálogo pero sin resultados (no hay ceros inventados). |
| 4 | `obtener_resultados` A → `particion=test`, S=8 D=2 I=1 N=100, `wer=0.11`. B → S=5 D=3 I=1 N=100, `wer=0.09`. | El WER ya viene calculado por la capa determinista (no lo calcula el LLM). |
| 5 | El modelo escribe un JSON como texto (modo *prompted*) con `estado=comparacion`, las dos medidas con su `fila`, `ganador=B` y las fuentes `demo:es:A`, `demo:es:B`. | Valida contra la unión discriminada de Pydantic y además el verificador recalcula cifras, fuentes y decisión: **sin hallazgos**. |
| 6 | Ejecución terminada con `salida_final`. Auditoría del servidor: 3 llamadas, todas `ok`, ninguna denegada. | Los cuatro niveles de la evaluación salen en verde (éxito, estructura, coherencia, permisos). |

Lo que se ve aquí: el camino feliz son **2 solicitudes** al modelo (planificar llamadas + responder). El coste de MCP es el arranque
del subproceso (~1,3 s); el resto de la ejecución cuesta lo mismo que en local (mismos tokens: 6683 de media en las dos configuraciones).

---

## Traza 2 — Abstención correcta: `pydantic_mcp`, caso C04 (A vs D, D sin resultados), tanda `v3_verificada`

Resultado: `datos_insuficientes`, motivo `sistema_sin_resultados`. 5,7 s · req 2 · tools 3 · reint 0 · tok 5384/165.

| # | Qué pasa | Comentario |
|---|---|---|
| 1 | Llamadas: `listar_sistemas(demo, es)`, `obtener_resultados(demo, es, A)`, `obtener_resultados(demo, es, D)`. | Pide justo lo que necesita. |
| 2 | A → fila `demo:es:A`, `wer=0.11`. D → `disponibilidad="sin_resultados"`, `detalle="No hay resultados de D en demo/es. No se inventan ni se sustituyen por ceros."` | Es el punto clave del caso: D **no está** en los datos. El modelo no ve ningún `0`. |
| 3 | JSON final: `estado=datos_insuficientes`, `motivo=sistema_sin_resultados`, `corpus=demo`, `idioma=es`, `sistemas=["D"]`, `detalle="El sistema D no tiene resultados para el corpus demo y el idioma español."` | Sin WER, sin ganador (el esquema de `DatosInsuficientes` ni siquiera tiene esos campos). |
| 4 | El verificador comprueba contra los datos que de verdad `demo/es/D` no existe: **justificada**. | Una abstención también se verifica: si el modelo se hubiera abstenido teniendo datos, el hallazgo sería `abstencion_injustificada`. |

Variante con control de acceso (caso C09, corpus `privado`, misma tanda): el modelo pide tres veces el corpus `privado`; el
**servidor** devuelve `corpus_no_autorizado` (`"solo se permite ['demo']"`, `corregible=false`) y lo anota en la auditoría; el modelo
responde `acceso_denegado` (con un reintento de contrato porque faltaba `corpus`). La denegación no depende de que el modelo se
porte bien: está en el servidor.

---

## Traza 3 — Fallo observado: `pydantic_mcp`, caso C07 (misma pareja pero partición `test` vs `dev`)

### 3a. El fallo (tanda `v2_verificada`)

Resultado: **sin salida** (`salida_invalida`, `Exceeded maximum output retries (2)`). 11,1 s · req 4 · tools 3 · tok 12361/407.

**Petición:** «Compara los sistemas A y B en español usando el corpus demo.» (datos del escenario `incompatibles.json`).
**Acciones:** `listar_sistemas{corpus:demo, idioma:es}`, `obtener_resultados{corpus:demo, idioma:es, sistema:A}`, `obtener_resultados{corpus:demo, idioma:es, sistema:B}`.
**Observaciones:** `demo:es:A` partición `test`, WER 0,11; `demo:es:B` partición `dev`, WER 0,09 (mismos metadatos en todo lo demás).
(Los mensajes de reintento que la aplicación devuelve al modelo no se guardan en la traza: solo se ven los textos que el modelo produce.)

1. Herramientas: A es `test`, B es `dev` (`obtener_resultados` lo dice en el campo `particion`).
2. **Intento 1** del modelo: `comparacion` con B ganador, y en `limitaciones` incluso menciona «la partición de desarrollo».
   Estructuralmente es válida y falsa a la vez: compara filas **no comparables**. El verificador la rechaza (`filas_no_comparables`).
3. **Intento 2**: ya se abstiene bien (`filas_no_comparables`, explica que A está en `test` y B en `dev`) y cita las fuentes, pero **sin `corpus` ni `idioma`**: el contrato exige esos campos y devuelve «falta `corpus`».
4. **Intento 3**: añade `corpus` e `idioma`, pero **se le olvida `fuentes`** (que sí había puesto antes). Se agotan los 2 reintentos.

Diagnóstico: el modelo entendía el problema (al segundo intento ya dice lo correcto). Fallaba el **bucle de corrección**: el contrato devolvía
**un solo error cada vez**, y el modelo, al arreglarlo, reescribía la respuesta y perdía un campo que estaba bien. El mismo patrón apareció en
C07b (pydantic local y MCP) y, con otro síntoma, en C04 de smolagents (`limite_excedido`).

### 3b. Modificación derivada del fallo (v3)

* `contratos.py`: el validador de `DatosInsuficientes` lista **todos** los campos que faltan a la vez y pide «reenvía la respuesta COMPLETA
  manteniendo los campos que ya eran correctos».
* `verificador.py`: el hallazgo `filas_no_comparables` incluye **la abstención correcta** como sugerencia
  (`estado=datos_insuficientes, motivo=filas_no_comparables, corpus=…, idioma=…, fuentes=[…]`), de modo que el primer rechazo ya enseña qué responder.

Es un cambio de **retroalimentación al modelo**, no toca las reglas del dominio ni los datos ni los límites.

### 3c. Después (tanda `v3_verificada`)

Resultado: `datos_insuficientes` / `filas_no_comparables`, **éxito**. 11,2 s · req 3 · tools 3 · tok 8909/389.
Primer intento: la misma comparación inválida → rechazo del verificador con la sugerencia → segundo intento: abstención completa con `corpus`, `idioma` y las
dos `fuentes`. De 4 solicitudes sin salida a 3 con la respuesta correcta.

Antes/después sobre los casos afectados y los de no regresión (misma tanda de casos, mismos límites; ver `antes_despues.md`):

| caso | smolagents v2 → v3 | pydantic_local v2 → v3 | pydantic_mcp v2 → v3 |
|---|---|---|---|
| C04 | 0 → 1 | 1 → 1 | 1 → 1 |
| C07 | 0 → 1 | 0 → 1 | 0 → 1 |
| C07b | 1 → 1 | 0 → 1 | 0 → 1 |
| C01, C03, C05, C08, C09 (no regresión) | todos 1 → 1 (C01: 3/3 → 3/3) | todos 1 → 1 | todos 1 → 1 |

Cada celda es una sola ejecución (salvo C01, 3), así que es **evidencia cualitativa**: sirve para ver que el mecanismo corrige el fallo y que no rompe
lo que funcionaba, no para estimar tasas.

---

## Otros dos fallos observados (para el análisis)

* **«Válido pero falso» en smolagents, caso C07 (tanda `base`)**: el agente devolvió con `final_answer` una comparación bien formada (B gana) con las dos
  particiones mezcladas, y en `limitaciones` escribió «usando la partición dev para B y test para A». Sin verificador habría pasado por buena; el verificador
  la rechaza con `[filas_no_comparables] las filas difieren en particion`. Aquí la validez estructural no basta.
* **Fallo sin resolver: smolagents inventa el idioma, caso C06 (3/3 en todas las tandas)**: la pregunta es «Compara A y B usando el corpus demo» (sin idioma).
  El `ToolCallingAgent` llama a `listar_sistemas(demo, **es**)` por su cuenta, y como todo lo que devuelve es coherente, responde con la comparación en español.
  El verificador no puede detectarlo porque solo ve los datos, no el texto del usuario. Los dos agentes de Pydantic AI sí piden aclaración (3/3), con la misma
  política y el mismo modelo, lo que sugiere (hipótesis, no medida) que influye la forma de la interacción: en smolagents el modelo
  tiene que emitir una acción en cada paso y tiende a «hacer algo». Se deja documentado como límite.

---

## Ejecución no realizada: `CodeAgent` de smolagents

`CodeAgent` (el modelo escribe Python que llama a las herramientas) **no se ha ejecutado**: ejecutar código generado por un modelo exige un entorno aislado
(Docker/E2B) que no se ha desplegado. Consta como fila `smolagents_codeagent, todos` en `no_ejecutadas.csv`, con el motivo. En la memoria se analiza qué cambiaría
(menos solicitudes por composición de llamadas en un solo bloque, pero más superficie de ataque y trazas menos auditables).
