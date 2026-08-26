# Hallazgos del proyecto

Registro de observaciones, hipótesis y métricas obtenidas durante las
simulaciones de cada versión del modelo de gobernanza.

---

## 2026-08-22 — Primera simulación con v1 (vecindario local)
- Ejecuté `simular_actividad.py --num-invitaciones 50 --prob-si 0.6 --notas "prueba inicial"`.
- Tasa de aprobación: 62% (mayor a lo esperado).
- Los candidatos con antecedentes judiciales fueron rechazados en un 78%.
- **Hipótesis:** el sesgo por judicial es demasiado fuerte; reducir de -0.15 a -0.10 en próxima simulación.

---

## 2026-08-23 — Simulación con homofilia (v1 extendida)
- Cambié parámetros: `--prob-si 0.5 --notas "homofilia activa"`.
- Se observa que los votantes de nivel alto tienden a votar SÍ a candidatos de nivel alto (82%).
- **Pendiente:** revisar si esto introduce sesgo de clase en la red.

---

## Versión 1 — Admisión por vecindario local (resultados consolidados)
- **Red:** 25 usuarios activos, 5 fundadores, 6 asignaciones de hermanos.
- **Votación:** 40 votos emitidos (28 SÍ, 6 NO, 6 abstenciones).
- **Invitaciones:** 10 aprobadas, 0 caducadas.
- **Observación:** El cuórum se alcanzó en todas las propuestas, lo que sugiere que el vecindario local es efectivo para redes pequeñas.

---

## Versión 2 — Jurado inter‑rama ad‑hoc
- **Votación total:** 108 votos (71 locales, 37 de jurado).
- **Distribución por rol:**
  - Local: 51 SÍ, 11 NO, 9 abst.
  - Jurado: 29 SÍ, 7 NO, 1 abst.
- **Invitaciones:** 19 aprobadas, 1 caducada.
- **Observación:** La participación del jurado no reduce la tasa de aprobación; los jurados tienden a votar SÍ en proporción similar a los locales.

---

## Versión 3 — Vecinos persistentes inter‑rama balanceados
- **Ramas:** 5 raíces; 172 asignaciones inter‑rama activas, 0 reemplazos.
- **Carga:** mínima 0, máxima 11, promedio 4.0 asignaciones por usuario.
- **Delegaciones:** 2 solicitudes, ambas rechazadas.
- **Votación:**
  - Local: 23 SÍ, 6 NO, 7 abst.
  - Persistente: 23 SÍ, 8 NO, 5 abst.
- **Invitaciones:** 9 aprobadas, 1 caducada.
- **Observación:** El balanceo funciona, pero la delegación no se utiliza; los vecinos persistentes votan de forma similar a los locales.

---

## Versión 4 — Reciprocidad y gestión de inactividad
- **Miembros:** 61 activos (100%), 0 inactivos.
- **Asignaciones de hermanos:** 31 vigentes, 0 reemplazos por inactividad.
- **Votación:** 143 votos totales:
  - Local: 40 SÍ, 8 NO, 16 abst.
  - Persistente: 50 SÍ, 15 NO, 14 abst.
- **Invitaciones:** 18 aprobadas, 2 caducadas.
- **Observación:** La inactividad no fue un problema en esta simulación. Los votos persistentes superan a los locales en número, lo que refleja el crecimiento de la red.

---

## Versión 5 — Sanciones, advertencias y expulsiones
- **Estados disciplinarios:** 1 suspendido cautelar, 0 suspendidos por sanción, 0 expulsados.
- **Procesos:** 1 archivado (`resolved_archived`).
- **Jurados:** 14 asignados, 0 recusados.
- **Decisiones del jurado:** 8 expulsión, 4 archivo, 2 suspensión.
- **Suspensiones cautelares:** 1 registrada y vigente.
- **Observación:** El sistema disciplinario funciona; aunque solo hubo un proceso, el jurado mostró una tendencia a decisiones severas (mayoría de expulsiones). La suspensión cautelar se aplicó correctamente.

---

## Versión 6 — Capa técnica (mandatos, Shamir, firma de acciones)
- **Mandatos técnicos:** 1 registrado, 0 vigentes, 1 revocado por cuórum.
- **Custodia Shamir:** 5 fragmentos, 5 custodios, umbral promedio k=3, total n=5.
- **Acciones firmadas:** 3 registros (backup, actualización de configuración, parche de seguridad), ejecutadas por 1 usuario único.
- **Cuórum de revocación:** 40 miembros activos necesarios (sobre 60 activos).
- **Observación:** La capa técnica está operativa; la revocación de mandatos requiere el cuórum de 2/3. Los metadatos de Shamir no almacenan secretos, lo que cumple con la seguridad esperada.

---

## Versión 7 — Auto‑gobernanza y modificación versionada del reglamento
- **Reglamento:** 5 versiones históricas, 4 vigentes, 1 cerrada.
- **Propuestas:** 1 propuesta creada y aprobada.
- **Votación:** 500 votos emitidos (334 SÍ, 83 NO, 83 abstenciones).
- **Cuórum requerido:** 334 votos (2/3 de 500 activos) — exactamente alcanzado.
- **Observación:** El mecanismo de cambio reglamentario funciona con el cuórum exigido. La inmutabilidad de las reglas históricas está garantizada (triggers). La participación fue del 100% de los activos.

---

## Conclusiones generales
- El modelo evoluciona de forma aditiva, preservando la historia y permitiendo análisis retrospectivo.
- La integración inter‑rama (v2→v4) mejora la representatividad sin perjudicar la tasa de aprobación.
- Los mecanismos de inactividad (v4), disciplina (v5) y auto‑gobernanza (v7) se comportan según lo esperado.
- La capa técnica (v6) proporciona seguridad y trazabilidad sin almacenar secretos sensibles.
- El cuórum de 2/3 resulta alcanzable en redes de tamaño medio (500 miembros) con alta participación.