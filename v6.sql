-- ============================================================
-- v6 — Capa técnica
-- ============================================================
--
-- Soporta:
--
-- 1. Mandatos técnicos electos y revocables.
-- 2. Custodia distribuida mediante Shamir Secret Sharing.
-- 3. Registro público y firmado de acciones técnicas.
--
-- Migración aditiva:
-- no elimina ni renombra estructuras anteriores.
-- ============================================================


-- ============================================================
-- 1. ROLES TÉCNICOS
-- ============================================================

CREATE TABLE technical_roles (

    user_id UUID NOT NULL
        REFERENCES users(id),

    granted_at TIMESTAMPTZ NOT NULL,

    granted_until TIMESTAMPTZ NOT NULL,

    revoked_at TIMESTAMPTZ,

    revoked_by UUID
        REFERENCES users(id),

    PRIMARY KEY (
        user_id,
        granted_at
    ),

    CHECK (
        granted_until > granted_at
    ),

    CHECK (
        revoked_at IS NULL
        OR revoked_at >= granted_at
    ),

    CHECK (
        (
            revoked_at IS NULL
            AND revoked_by IS NULL
        )
        OR
        (
            revoked_at IS NOT NULL
            AND revoked_by IS NOT NULL
        )
    )
);


-- ============================================================
-- 2. FRAGMENTOS DE CLAVE
-- ============================================================
--
-- IMPORTANTE:
--
-- La tabla NO guarda el contenido secreto del fragmento.
--
-- Solo registra:
--
-- - identificador del fragmento;
-- - custodio;
-- - umbral necesario;
-- - total de fragmentos;
-- - fecha de creación.
--
-- Los fragmentos reales deben mantenerse separados.
-- ============================================================

CREATE TABLE key_shards (

    shard_id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    custodian_id UUID NOT NULL
        REFERENCES users(id),

    threshold_k INTEGER NOT NULL,

    total_n INTEGER NOT NULL,

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT now(),

    CHECK (
        threshold_k >= 2
    ),

    CHECK (
        total_n >= threshold_k
    )
);


-- ============================================================
-- 3. LOG PÚBLICO DE ACCIONES TÉCNICAS
-- ============================================================

CREATE TABLE technical_action_log (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    action_type TEXT NOT NULL,

    executed_by UUID NOT NULL
        REFERENCES users(id),

    target_ref TEXT NOT NULL,

    executed_at TIMESTAMPTZ NOT NULL
        DEFAULT now(),

    signature TEXT NOT NULL
);


-- ============================================================
-- 4. ÍNDICES
-- ============================================================

CREATE INDEX idx_technical_roles_user
ON technical_roles(user_id);


CREATE INDEX idx_technical_roles_until
ON technical_roles(granted_until);


CREATE INDEX idx_key_shards_custodian
ON key_shards(custodian_id);


CREATE INDEX idx_technical_log_executor
ON technical_action_log(executed_by);


CREATE INDEX idx_technical_log_date
ON technical_action_log(executed_at);


-- ============================================================
-- 5. COMENTARIOS
-- ============================================================

COMMENT ON TABLE technical_roles IS
'Mandatos técnicos electos, acotados temporalmente y revocables.';


COMMENT ON TABLE key_shards IS
'Metadatos de fragmentos distribuidos de claves. El secreto no se almacena en la base de datos.';


COMMENT ON TABLE technical_action_log IS
'Registro público firmado de acciones realizadas por la capa técnica.';


COMMENT ON COLUMN technical_action_log.signature IS
'Firma criptográfica que permite verificar posteriormente la acción.';
