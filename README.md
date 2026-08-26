# Base_de_Datos_1_2026

## Evolución del modelo de datos

Cada versión es una **migración aditiva**: solo agrega tablas o columnas,
nunca borra ni renombra lo existente. Esto preserva la historia completa
de la red y permite que cualquier fila creada bajo una versión anterior
siga siendo legible bajo las versiones posteriores.

Los archivos de migración se ejecutan en orden (`v1.sql`, `v2.sql`, ...).

### v1 — Base: admisión por vecindario local
Archivo: `v1.sql`

Soporta el árbol de invitaciones, la votación con cuórum local y la
persistencia de hermanos vecinales sorteados.

Tablas: `users`, `invitations`, `votes`, `sibling_assignments`.

### v2 — Tejido inter-rama mediante jurado ad-hoc
Archivo: `v2.sql`

Agrega el origen del voto (`local` o `jurado`) en la tabla `votes`,
permitiendo que miembros de otras ramas participen en las votaciones
de admisión de forma determinista.

### v3 — Vecinos persistentes inter-rama balanceados
Archivo: `v3.sql`

Introduce la asignación persistente de vecinos inter‑rama con balanceo de
carga (`round‑robin`). Cada nuevo miembro recibe un vecino de cada otra
rama, que votará en todas sus futuras propuestas. Además, se añade el
mecanismo de delegación voluntaria de estas asignaciones.

Tablas nuevas: `inter_rama_assignments`, `delegation_requests`.
Columna en `users`: `rama_root_id`.

### v4 — Reciprocidad e inactividad
Archivo: `v4.sql`

Gestiona la inactividad de los miembros para que no bloqueen el cuórum.
Se añade el estado `inactive` y el campo `last_active_at`, con triggers
que actualizan la actividad al votar o proponer. Los vecinos inactivos
pueden ser reemplazados.

### v5 — Sanciones, advertencias y expulsiones
Archivo: `v5.sql`

Implementa el sistema disciplinario: procesos, descargos, jurados
sorteados determinísticamente, decisiones (archivo, amonestación,
suspensión, expulsión) y suspensiones cautelares (máximo 30 días).

Nuevos tipos: `disciplinary_status`, `disciplinary_decision`.
Tablas: `disciplinary_processes`, `defense_responses`, `juries`,
`jury_decisions`, `cautelary_suspensions`.

### v6 — Capa técnica
Archivo: `v6.sql`

Soporta mandatos técnicos electos y revocables, custodia distribuida
de claves mediante Shamir Secret Sharing (solo metadatos, el secreto
no se almacena en la BD) y un registro público firmado de acciones
técnicas (Ed25519).

Tablas: `technical_roles`, `key_shards`, `technical_action_log`.

### v7 — Auto‑gobernanza
Archivo: `v7.sql`

Permite modificar el reglamento mediante propuestas versionadas.
Cada regla tiene un historial inmutable; las propuestas requieren
votación de toda la red activa con cuórum de 2/3.

Tablas: `rules`, `rule_proposals`, `rule_votes`.
Triggers que impiden la modificación o borrado de versiones históricas.

---

## Resultados de simulación por versión

A continuación se resumen los principales resultados obtenidos al ejecutar
las simulaciones con cada versión (extraídos de `documentacion.org`).

| Versión | Miembros activos | Invitaciones aprobadas | Votos totales | Observaciones clave |
|---------|------------------|------------------------|---------------|----------------------|
| **v1**  | 25               | 10                     | 40            | Alta tasa de aprobación (100% de las invitaciones alcanzaron cuórum). |
| **v2**  | (no especificado) | 19                     | 108           | Integración de jurado inter‑rama: 37 votos de jurado; aprobación estable. |
| **v3**  | (no especificado) | 9                      | 72            | Asignaciones inter‑rama balanceadas (promedio 4 por usuario). 2 solicitudes de delegación rechazadas. |
| **v4**  | 61               | 18                     | 143           | Sin inactivos; reemplazo de hermanos no necesario. Votos de persistentes ligeramente superiores a locales. |
| **v5**  | 61 (activos)     | —                      | —             | 1 proceso disciplinario archivado; 14 jurados asignados; decisión mayoritaria de expulsión (8 de 14). 1 suspensión cautelar vigente. |
| **v6**  | 60               | —                      | —             | 1 mandato técnico revocado; 5 fragmentos Shamir distribuidos; 3 acciones técnicas firmadas. Cuórum de revocación = 40. |
| **v7**  | 500              | —                      | 500           | 1 propuesta de cambio reglamentario aprobada con 334 votos a favor (justo el cuórum de 2/3). |

> **Nota:** Los resultados corresponden a simulaciones sintéticas y sirven para validar el comportamiento de cada capa del modelo.

## Cómo aplicar las migraciones

```bash
psql -d gobernanza -f v1.sql
psql -d gobernanza -f v2.sql
psql -d gobernanza -f v3.sql
psql -d gobernanza -f v4.sql
psql -d gobernanza -f v5.sql
psql -d gobernanza -f v6.sql
psql -d gobernanza -f v7.sql
