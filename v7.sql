-- ============================================================
-- v7 — Auto-gobernanza
-- ============================================================
--
-- Permite modificar el reglamento mediante:
--
-- 1. Reglas versionadas.
-- 2. Propuestas de modificación.
-- 3. Votación de toda la red activa.
-- 4. Cuórum elevado de 2/3.
--
-- Las reglas mantienen su historia.
--
-- Migración aditiva:
-- no elimina estructuras anteriores.
-- ============================================================


-- ============================================================
-- 1. ESTADO DE PROPUESTAS
-- ============================================================

CREATE TYPE rule_proposal_status AS ENUM (
    'open',
    'approved',
    'rejected',
    'expired'
);


-- ============================================================
-- 2. REGLAS VERSIONADAS
-- ============================================================

CREATE TABLE rules (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    version INTEGER NOT NULL,

    rule_key TEXT NOT NULL,

    body TEXT NOT NULL,

    effective_from TIMESTAMPTZ NOT NULL,

    effective_until TIMESTAMPTZ,

    UNIQUE (
        rule_key,
        version
    ),

    CHECK (
        version >= 1
    ),

    CHECK (
        effective_until IS NULL
        OR effective_until > effective_from
    )
);


-- ============================================================
-- 3. SOLO UNA VERSIÓN VIGENTE POR REGLA
-- ============================================================

CREATE UNIQUE INDEX idx_rules_one_current
ON rules(rule_key)
WHERE effective_until IS NULL;


-- ============================================================
-- 4. PROPUESTAS DE CAMBIO
-- ============================================================

CREATE TABLE rule_proposals (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    proposer_id UUID NOT NULL
        REFERENCES users(id),

    current_rule_id UUID NOT NULL
        REFERENCES rules(id),

    proposed_body TEXT NOT NULL,

    opened_at TIMESTAMPTZ NOT NULL,

    closes_at TIMESTAMPTZ NOT NULL,

    status rule_proposal_status NOT NULL
        DEFAULT 'open',

    CHECK (
        closes_at >=
        opened_at + INTERVAL '14 days'
    )
);


-- ============================================================
-- 5. VOTOS SOBRE REGLAS
-- ============================================================

CREATE TABLE rule_votes (

    proposal_id UUID NOT NULL
        REFERENCES rule_proposals(id),

    voter_id UUID NOT NULL
        REFERENCES users(id),

    choice vote_choice NOT NULL,

    voted_at TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (
        proposal_id,
        voter_id
    )
);


-- ============================================================
-- 6. ÍNDICES
-- ============================================================

CREATE INDEX idx_rules_key
ON rules(rule_key);


CREATE INDEX idx_rule_proposals_proposer
ON rule_proposals(proposer_id);


CREATE INDEX idx_rule_proposals_status
ON rule_proposals(status);


CREATE INDEX idx_rule_votes_voter
ON rule_votes(voter_id);


-- ============================================================
-- 7. PROTEGER HISTORIA DE rules
-- ============================================================
--
-- Una versión de regla no puede cambiar
-- su contenido después de ser creada.
--
-- Solo se permite completar effective_until
-- cuando aparece una versión posterior.
-- ============================================================

CREATE OR REPLACE FUNCTION proteger_regla_versionada()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    IF NEW.id <> OLD.id
       OR NEW.version <> OLD.version
       OR NEW.rule_key <> OLD.rule_key
       OR NEW.body <> OLD.body
       OR NEW.effective_from <> OLD.effective_from
    THEN

        RAISE EXCEPTION
        'Una versión de regla es inmutable.';

    END IF;


    IF OLD.effective_until IS NOT NULL
       AND NEW.effective_until
           IS DISTINCT FROM OLD.effective_until
    THEN

        RAISE EXCEPTION
        'Una regla histórica cerrada no puede modificarse.';

    END IF;


    IF OLD.effective_until IS NULL
       AND NEW.effective_until IS NULL
    THEN

        RETURN NEW;

    END IF;


    IF OLD.effective_until IS NULL
       AND NEW.effective_until IS NOT NULL
    THEN

        RETURN NEW;

    END IF;


    RAISE EXCEPTION
    'Modificación de regla no permitida.';

END;
$$;


CREATE TRIGGER trg_proteger_regla_versionada
BEFORE UPDATE ON rules
FOR EACH ROW
EXECUTE FUNCTION proteger_regla_versionada();


-- ============================================================
-- 8. IMPEDIR BORRADO DE HISTORIA
-- ============================================================

CREATE OR REPLACE FUNCTION impedir_borrado_regla()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    RAISE EXCEPTION
    'Las versiones históricas de reglas no pueden eliminarse.';

END;
$$;


CREATE TRIGGER trg_impedir_borrado_regla
BEFORE DELETE ON rules
FOR EACH ROW
EXECUTE FUNCTION impedir_borrado_regla();


-- ============================================================
-- 9. COMENTARIOS
-- ============================================================

COMMENT ON TABLE rules IS
'Historial versionado e inmutable del reglamento.';


COMMENT ON TABLE rule_proposals IS
'Propuestas de modificación de una regla vigente.';


COMMENT ON TABLE rule_votes IS
'Votos emitidos por la red activa sobre cambios al reglamento.';
