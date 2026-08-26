-- ============================================================
-- v1 — Admisión por vecindario local
-- ============================================================
--
-- Implementa:
--   - árbol de invitaciones
--   - propuestas de admisión
--   - votación
--   - hermanos vecinales persistentes
--
-- Esta es la primera versión del modelo.
-- ============================================================


-- ------------------------------------------------------------
-- Extensión para generar UUID
-- ------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ------------------------------------------------------------
-- Tipos enumerados
-- ------------------------------------------------------------

CREATE TYPE member_status AS ENUM (
    'active'
);

CREATE TYPE invitation_status AS ENUM (
    'open',
    'closed_approved',
    'closed_rejected',
    'expired'
);

CREATE TYPE vote_choice AS ENUM (
    'yes',
    'no',
    'abstain'
);


-- ------------------------------------------------------------
-- Usuarios
-- ------------------------------------------------------------

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    display_name TEXT NOT NULL,

    inviter_id UUID REFERENCES users(id),

    principles_accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    status member_status NOT NULL DEFAULT 'active'
);


-- ------------------------------------------------------------
-- Invitaciones
-- ------------------------------------------------------------

CREATE TABLE invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    proposer_id UUID NOT NULL REFERENCES users(id),

    candidate_email TEXT NOT NULL,

    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    closes_at TIMESTAMPTZ NOT NULL,

    status invitation_status NOT NULL DEFAULT 'open'
);


-- ------------------------------------------------------------
-- Votos
-- ------------------------------------------------------------

CREATE TABLE votes (
    invitation_id UUID NOT NULL
        REFERENCES invitations(id),

    voter_id UUID NOT NULL
        REFERENCES users(id),

    choice vote_choice NOT NULL,

    reason TEXT,

    cast_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (invitation_id, voter_id)
);


-- ------------------------------------------------------------
-- Hermanos vecinales
-- ------------------------------------------------------------

CREATE TABLE sibling_assignments (
    user_id UUID NOT NULL
        REFERENCES users(id),

    sibling_id UUID NOT NULL
        REFERENCES users(id),

    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    replaced_by UUID REFERENCES users(id),

    replaced_at TIMESTAMPTZ,

    PRIMARY KEY (user_id, sibling_id)
);
