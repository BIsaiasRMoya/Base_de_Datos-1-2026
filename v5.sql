-- ============================================================
-- v5 — Sanciones, advertencias y expulsiones
-- ============================================================
--
-- Agrega:
--   - estados disciplinarios de usuarios
--   - procesos disciplinarios
--   - descargos
--   - jurados
--   - decisiones del jurado
--   - suspensiones cautelares
--
-- Migración aditiva:
-- no elimina ni renombra estructuras anteriores.
-- ============================================================


-- ============================================================
-- 1. NUEVOS ESTADOS DE USUARIO
-- ============================================================

ALTER TYPE member_status
ADD VALUE 'suspended_cautelar';

ALTER TYPE member_status
ADD VALUE 'suspended_sanction';

ALTER TYPE member_status
ADD VALUE 'expelled';


-- ============================================================
-- 2. ESTADO DEL PROCESO DISCIPLINARIO
-- ============================================================
--
-- Estos nombres concretos son una decisión de implementación
-- para representar las etapas descritas por la propuesta.
-- ============================================================

CREATE TYPE disciplinary_status AS ENUM (
    'open',
    'defense',
    'jury',
    'resolved_archived',
    'resolved_warning',
    'resolved_suspension',
    'pending_expulsion_review',
    'resolved_expulsion'
);


-- ============================================================
-- 3. DECISIONES DEL JURADO
-- ============================================================

CREATE TYPE disciplinary_decision AS ENUM (
    'archive',
    'warning',
    'suspension',
    'expulsion'
);


-- ============================================================
-- 4. PROCESOS DISCIPLINARIOS
-- ============================================================

CREATE TABLE disciplinary_processes (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    complainant_id UUID NOT NULL
        REFERENCES users(id),

    accused_id UUID NOT NULL
        REFERENCES users(id),

    complaint_body TEXT NOT NULL,

    evidence_refs TEXT[] NOT NULL
        DEFAULT ARRAY[]::TEXT[],

    opened_at TIMESTAMPTZ NOT NULL
        DEFAULT now(),

    status disciplinary_status NOT NULL
        DEFAULT 'open',

    CHECK (
        complainant_id <> accused_id
    )
);


-- ============================================================
-- 5. DESCARGO
-- ============================================================

CREATE TABLE defense_responses (

    process_id UUID PRIMARY KEY
        REFERENCES disciplinary_processes(id),

    body TEXT NOT NULL,

    submitted_at TIMESTAMPTZ NOT NULL
        DEFAULT now()
);


-- ============================================================
-- 6. JURADOS
-- ============================================================

CREATE TABLE juries (

    process_id UUID NOT NULL
        REFERENCES disciplinary_processes(id),

    juror_id UUID NOT NULL
        REFERENCES users(id),

    sorted_at TIMESTAMPTZ NOT NULL
        DEFAULT now(),

    recused BOOLEAN NOT NULL
        DEFAULT FALSE,

    recusal_reason TEXT,

    PRIMARY KEY (
        process_id,
        juror_id
    ),

    CHECK (
        recused = FALSE
        OR recusal_reason IS NOT NULL
    )
);


-- ============================================================
-- 7. DECISIONES DE JURADOS
-- ============================================================

CREATE TABLE jury_decisions (

    process_id UUID NOT NULL,

    juror_id UUID NOT NULL,

    decision disciplinary_decision
        NOT NULL,

    reasoning TEXT NOT NULL,

    decided_at TIMESTAMPTZ NOT NULL
        DEFAULT now(),

    PRIMARY KEY (
        process_id,
        juror_id
    ),

    FOREIGN KEY (
        process_id,
        juror_id
    )
    REFERENCES juries(
        process_id,
        juror_id
    )
);


-- ============================================================
-- 8. SUSPENSIONES CAUTELARES
-- ============================================================

CREATE TABLE cautelary_suspensions (

    user_id UUID NOT NULL
        REFERENCES users(id),

    requested_by UUID NOT NULL
        REFERENCES users(id),

    ratified_by UUID NOT NULL
        REFERENCES users(id),

    started_at TIMESTAMPTZ NOT NULL,

    expires_at TIMESTAMPTZ NOT NULL,

    lifted_at TIMESTAMPTZ,

    PRIMARY KEY (
        user_id,
        started_at
    ),

    CHECK (
        expires_at > started_at
    ),


    CHECK (
    expires_at <=
    started_at + INTERVAL '720 hours'
    )


);


-- ============================================================
-- 9. ÍNDICES
-- ============================================================

CREATE INDEX idx_disciplinary_accused
ON disciplinary_processes(accused_id);


CREATE INDEX idx_disciplinary_complainant
ON disciplinary_processes(complainant_id);


CREATE INDEX idx_disciplinary_status
ON disciplinary_processes(status);


CREATE INDEX idx_juries_juror
ON juries(juror_id);


CREATE INDEX idx_jury_decisions_process
ON jury_decisions(process_id);


-- ============================================================
-- 10. COMENTARIOS
-- ============================================================

COMMENT ON TABLE disciplinary_processes IS
'Procesos disciplinarios introducidos en v5.';

COMMENT ON TABLE defense_responses IS
'Descargo presentado por la persona denunciada.';

COMMENT ON TABLE juries IS
'Jurados disciplinarios sorteados de forma determinista.';

COMMENT ON TABLE jury_decisions IS
'Decisiones individuales de los miembros del jurado.';

COMMENT ON TABLE cautelary_suspensions IS
'Suspensiones cautelares ratificadas, con duración máxima de 30 días.';
