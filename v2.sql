-- ============================================================
-- v2 — Tejido inter-rama mediante jurado ad-hoc
-- ============================================================
--
-- Esta migración se ejecuta DESPUÉS de v1.sql.
--
-- v2 no crea nuevas tablas.
-- Agrega a votes el origen del votante:
--
--   local       -> pertenece al vecindario local
--   jurado      -> sorteado desde otra rama
--   persistente -> reservado para la evolución v3
--
-- La migración es aditiva:
-- no elimina ni renombra estructuras de v1.
-- ============================================================


-- ------------------------------------------------------------
-- Tipo de rol del votante
-- ------------------------------------------------------------

CREATE TYPE voter_role AS ENUM (
    'local',
    'jurado',
    'persistente'
);


-- ------------------------------------------------------------
-- Agregar rol a votes
-- ------------------------------------------------------------

ALTER TABLE votes
ADD COLUMN voter_role voter_role;


-- ------------------------------------------------------------
-- Los votos que ya existían corresponden a v1,
-- por lo tanto todos eran votos locales.
-- ------------------------------------------------------------

UPDATE votes
SET voter_role = 'local'
WHERE voter_role IS NULL;


-- ------------------------------------------------------------
-- Desde v2 todo voto debe indicar su origen.
-- ------------------------------------------------------------

ALTER TABLE votes
ALTER COLUMN voter_role SET NOT NULL;


-- ------------------------------------------------------------
-- Por defecto un voto es local.
-- ------------------------------------------------------------

ALTER TABLE votes
ALTER COLUMN voter_role SET DEFAULT 'local';


COMMENT ON COLUMN votes.voter_role IS
'Origen del votante: local, jurado inter-rama o persistente.';
