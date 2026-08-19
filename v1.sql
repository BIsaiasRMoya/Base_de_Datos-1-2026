-- ============================================================
-- v1 — Base: admisión por vecindario local
-- Soporta árbol de invitaciones, votación con cuórum local,
-- y persistencia de hermanos vecinales sorteados.
-- ============================================================

-- Extensión para UUIDs (si no está habilitada)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enumeraciones para estados
CREATE TYPE member_status AS ENUM ('active');
CREATE TYPE invitation_status AS ENUM ('open', 'closed_approved', 'closed_rejected', 'expired');
CREATE TYPE vote_choice AS ENUM ('yes', 'no', 'abstain');

-- Tabla de usuarios (miembros de la red)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name TEXT NOT NULL,
    inviter_id UUID REFERENCES users(id) ON DELETE SET NULL,
    principles_accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status member_status NOT NULL DEFAULT 'active'
);

COMMENT ON TABLE users IS 'Miembros de la red. inviter_id = NULL para el grupo fundador (génesis).';
COMMENT ON COLUMN users.inviter_id IS 'Madrina/padrino que invitó a este usuario. NULL si es fundador.';

-- Tabla de propuestas de admisión
CREATE TABLE invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_email TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closes_at TIMESTAMPTZ NOT NULL,
    status invitation_status NOT NULL DEFAULT 'open'
);

COMMENT ON TABLE invitations IS 'Propuestas para admitir nuevos miembros.';
COMMENT ON COLUMN invitations.closes_at IS 'Fecha límite para votar (ej. 7 días después de opened_at).';

-- Tabla de votos emitidos en propuestas de admisión
CREATE TABLE votes (
    invitation_id UUID NOT NULL REFERENCES invitations(id) ON DELETE CASCADE,
    voter_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    choice vote_choice NOT NULL,
    reason TEXT,
    cast_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (invitation_id, voter_id)
);

COMMENT ON TABLE votes IS 'Votos de los vecinos sobre una invitación.';
COMMENT ON COLUMN votes.reason IS 'Motivo del voto (obligatorio para NO, opcional para SÍ/abstención).';

-- Tabla de asignación de hermanos vecinales (sorteo persistente)
CREATE TABLE sibling_assignments (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sibling_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    replaced_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    replaced_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, sibling_id)
);

COMMENT ON TABLE sibling_assignments IS 'Hermanos vecinales asignados por sorteo determinista al ingreso.';
COMMENT ON COLUMN sibling_assignments.replaced_by_user_id IS 'Usuario que reemplaza a este hermano (si se ha producido un reemplazo).';
COMMENT ON COLUMN sibling_assignments.replaced_at IS 'Momento en que este hermano fue reemplazado (NULL si sigue activo).';

-- Índices para mejorar rendimiento en consultas típicas
CREATE INDEX idx_users_inviter_id ON users(inviter_id);
CREATE INDEX idx_invitations_proposer_id ON invitations(proposer_id);
CREATE INDEX idx_invitations_status ON invitations(status);
CREATE INDEX idx_votes_invitation_id ON votes(invitation_id);
CREATE INDEX idx_votes_voter_id ON votes(voter_id);
CREATE INDEX idx_sibling_assignments_user_id ON sibling_assignments(user_id);
CREATE INDEX idx_sibling_assignments_sibling_id ON sibling_assignments(sibling_id);
