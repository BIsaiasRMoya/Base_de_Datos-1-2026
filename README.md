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

### v2 — Perfil extendido de usuarios (nivel socioeconómico y antecedentes)
Archivo: `v2.sql`

Agrega características adicionales a los usuarios sin modificar la tabla
`users` original:

- **`user_socioeconomic_profile`** (relación 1:1 con `users`): nivel
  socioeconómico, ocupación, nivel educativo, rango de ingreso.
- **`user_backgrounds`** (relación 1:N con `users`): antecedentes por
  usuario (laboral, educativo, judicial, referencias personales, etc.),
  con soporte de verificación por otro miembro de la red.

Nuevos tipos: `socioeconomic_level`, `background_type`.

## Cómo aplicar las migraciones

```bash
psql -d gobernanza -f v1.sql
psql -d gobernanza -f v2.sql
```

## Población de datos para v2 (Perfil extendido)

La versión 2 introduce las tablas `user_socioeconomic_profile` y `user_backgrounds`. Para generar datos sintéticos en estas tablas, tienes dos opciones:

1. **Usar `generar_red.py` modificado**: el script ya incluye la inserción de perfiles y antecedentes para cada usuario creado (ver sección de código). Ejecútalo con los parámetros deseados.

2. **Ejecutar `poblar_v2.py`** después de generar la red: este script recorre todos los usuarios activos y les asigna perfiles y antecedentes aleatorios.

```bash
python generar_red.py --total 100 --fundadores 5 --semilla 42
python poblar_v2.py   # si usas el script separado
```

## Evolución del modelo de datos

Cada versión es una migración aditiva.

### v3 — Persistencia del perfil del candidato en la invitación (v3.sql)

Agrega columnas a `invitations` para registrar el perfil simulado del candidato:

- `candidate_socioeconomic_level TEXT`: nivel socioeconómico.
- `candidate_backgrounds TEXT[]`: lista de antecedentes (ej. `{"judicial", "laboral"}`).

Esto permite analizar empíricamente:

- ¿Los antecedentes judiciales afectan la tasa de aprobación?
- ¿Existe homofilia socioeconómica en los votos?
- ¿Cómo se distribuye el éxito de admisión por perfil?

```bash
psql -d gobernanza -f v1.sql
psql -d gobernanza -f v2.sql
psql -d gobernanza -f v3.sql   # <-- nueva migración