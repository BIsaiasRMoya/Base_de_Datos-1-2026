-- ============================================================
-- v4 — Reciprocidad e inactividad
-- ============================================================
--
-- Agrega:
--   - last_active_at en users
--   - estado inactive
--   - actualización automática de actividad
--   - bloqueo de propuestas para usuarios inactivos
--
-- No crea nuevas tablas.
-- ============================================================


-- ------------------------------------------------------------
-- 1. Nuevo estado de usuario
-- ------------------------------------------------------------

ALTER TYPE member_status
ADD VALUE 'inactive';


-- ------------------------------------------------------------
-- 2. Última actividad
-- ------------------------------------------------------------

ALTER TABLE users
ADD COLUMN last_active_at TIMESTAMPTZ;


-- ------------------------------------------------------------
-- 3. Reconstruir actividad histórica
-- ------------------------------------------------------------
--
-- Para miembros existentes usamos la acción significativa
-- más reciente entre:
--
--   - ingreso a la red
--   - voto emitido
--   - propuesta iniciada
--
-- La propuesta indica que la actividad puede inferirse
-- desde votes e invitations.
-- ------------------------------------------------------------

UPDATE users u
SET last_active_at = GREATEST(

    u.principles_accepted_at,

    COALESCE(
        (
            SELECT MAX(v.cast_at)
            FROM votes v
            WHERE v.voter_id = u.id
        ),
        u.principles_accepted_at
    ),

    COALESCE(
        (
            SELECT MAX(i.opened_at)
            FROM invitations i
            WHERE i.proposer_id = u.id
        ),
        u.principles_accepted_at
    )
);


ALTER TABLE users
ALTER COLUMN last_active_at SET NOT NULL;


-- ------------------------------------------------------------
-- 4. Un voto cuenta como actividad
-- ------------------------------------------------------------
--
-- Además, votar reactiva inmediatamente
-- a una persona inactiva.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION actualizar_actividad_voto()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    UPDATE users
    SET
        last_active_at = GREATEST(
            last_active_at,
            NEW.cast_at
        ),
        status = 'active'
    WHERE id = NEW.voter_id;

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_actualizar_actividad_voto
AFTER INSERT ON votes
FOR EACH ROW
EXECUTE FUNCTION actualizar_actividad_voto();


-- ------------------------------------------------------------
-- 5. Proponer una admisión también cuenta como actividad
-- ------------------------------------------------------------
--
-- Un usuario inactive no puede realizar propuestas
-- hasta reactivarse.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validar_propuesta_y_actividad()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    estado member_status;
BEGIN

    SELECT status
    INTO estado
    FROM users
    WHERE id = NEW.proposer_id;

    IF estado IS NULL THEN

        RAISE EXCEPTION
        'El proponente no existe.';

    END IF;


    IF estado <> 'active' THEN

        RAISE EXCEPTION
        'El usuario está inactivo y no puede proponer admisiones.';

    END IF;


    UPDATE users
    SET last_active_at = GREATEST(
        last_active_at,
        NEW.opened_at
    )
    WHERE id = NEW.proposer_id;

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_validar_propuesta_actividad
BEFORE INSERT ON invitations
FOR EACH ROW
EXECUTE FUNCTION validar_propuesta_y_actividad();


COMMENT ON COLUMN users.last_active_at IS
'Fecha UTC de la última acción significativa del miembro.';
