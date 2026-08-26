-- ============================================================
-- v3 — Vecinos persistentes inter-rama balanceados
-- ============================================================
--
-- Extiende v2 incorporando:
--
-- 1. rama_root_id cacheado en users.
-- 2. vecinos inter-rama persistentes.
-- 3. solicitudes de delegación.
--
-- La migración es ADITIVA:
-- no elimina ni renombra estructuras anteriores.
-- ============================================================


-- ------------------------------------------------------------
-- 1. Guardar la raíz de rama de cada usuario
-- ------------------------------------------------------------

ALTER TABLE users
ADD COLUMN rama_root_id UUID REFERENCES users(id);


-- ------------------------------------------------------------
-- 2. Calcular rama_root_id para usuarios existentes
-- ------------------------------------------------------------
--
-- Cada fundador es raíz de su propia rama.
-- Los demás siguen inviter_id hasta alcanzar un fundador.
-- ------------------------------------------------------------

WITH RECURSIVE ramas AS (

    -- Fundadores
    SELECT
        id AS user_id,
        id AS rama_root_id
    FROM users
    WHERE inviter_id IS NULL

    UNION ALL

    -- Descendientes
    SELECT
        u.id AS user_id,
        r.rama_root_id
    FROM users u

    JOIN ramas r
        ON u.inviter_id = r.user_id
)

UPDATE users u
SET rama_root_id = r.rama_root_id
FROM ramas r
WHERE u.id = r.user_id;


-- ------------------------------------------------------------
-- 3. Vecinos persistentes inter-rama
-- ------------------------------------------------------------
--
-- Se agrega un id porque delegation_requests necesita
-- referirse inequívocamente a una asignación.
-- ------------------------------------------------------------

CREATE TABLE inter_rama_assignments (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL
        REFERENCES users(id),

    neighbor_id UUID NOT NULL
        REFERENCES users(id),

    other_rama_root_id UUID NOT NULL
        REFERENCES users(id),

    assigned_at TIMESTAMPTZ NOT NULL
        DEFAULT now(),

    replaced_by UUID
        REFERENCES users(id),

    replaced_at TIMESTAMPTZ,

    UNIQUE (
        user_id,
        other_rama_root_id,
        assigned_at
    )
);


-- ------------------------------------------------------------
-- 4. Delegación
-- ------------------------------------------------------------

CREATE TABLE delegation_requests (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    delegator_id UUID NOT NULL
        REFERENCES users(id),

    assignment_id UUID NOT NULL
        REFERENCES inter_rama_assignments(id),

    delegate_to_id UUID NOT NULL
        REFERENCES users(id),

    accepted BOOLEAN,

    decided_at TIMESTAMPTZ
);


-- ------------------------------------------------------------
-- 5. Índices
-- ------------------------------------------------------------

CREATE INDEX idx_users_rama_root
ON users(rama_root_id);


CREATE INDEX idx_inter_rama_user
ON inter_rama_assignments(user_id);


CREATE INDEX idx_inter_rama_neighbor
ON inter_rama_assignments(neighbor_id);


CREATE INDEX idx_inter_rama_other_root
ON inter_rama_assignments(other_rama_root_id);


-- ------------------------------------------------------------
-- 6. Vista de carga actual
-- ------------------------------------------------------------

CREATE VIEW inter_rama_assignment_count AS

SELECT
    u.id AS user_id,
    COUNT(a.id) AS assignment_count

FROM users u

LEFT JOIN inter_rama_assignments a
    ON a.neighbor_id = u.id
   AND a.replaced_at IS NULL

GROUP BY u.id;


COMMENT ON COLUMN users.rama_root_id IS
'Raíz del subárbol al que pertenece el usuario. Introducido en v3.';


COMMENT ON TABLE inter_rama_assignments IS
'Vecinos inter-rama persistentes asignados con balanceo de carga.';


COMMENT ON TABLE delegation_requests IS
'Solicitudes voluntarias para delegar una asignación inter-rama.';
