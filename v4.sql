-- ============================================================
-- v4 — Vecinos persistentes balanceados (inter-rama)
-- Migración ADITIVA sobre v1+v2+v3.
-- Agrega rama_root_id a users y tablas de asignaciones persistentes.
-- ============================================================

-- 1. Añadir columna rama_root_id a users (cache de la raíz del génesis)
ALTER TABLE users ADD COLUMN rama_root_id UUID REFERENCES users(id);

COMMENT ON COLUMN users.rama_root_id IS 'Raíz del génesis (miembro fundador) de la rama a la que pertenece este usuario. Se calcula al ingresar y se cachea.';

-- 2. Tabla de asignaciones persistentes inter-rama
CREATE TABLE inter_rama_assignments (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    neighbor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    other_rama_root_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    replaced_by UUID REFERENCES users(id) ON DELETE SET NULL,
    replaced_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, neighbor_id)
);

COMMENT ON TABLE inter_rama_assignments IS 'Vecinos persistentes de otras ramas asignados al momento del ingreso.';
COMMENT ON COLUMN inter_rama_assignments.other_rama_root_id IS 'Raíz de la rama del vecino (para saber de qué rama proviene).';

-- 3. Tabla de solicitudes de delegación (para reasignar carga)
CREATE TABLE delegation_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delegator_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL,  -- referencia a inter_rama_assignments (no FK directa por simplicidad)
    delegate_to_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    accepted BOOLEAN DEFAULT FALSE,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE delegation_requests IS 'Solicitudes para transferir una asignación inter-rama a otra persona.';

-- Índices para consultas comunes
CREATE INDEX idx_inter_rama_assignments_user_id ON inter_rama_assignments(user_id);
CREATE INDEX idx_inter_rama_assignments_neighbor_id ON inter_rama_assignments(neighbor_id);
CREATE INDEX idx_inter_rama_assignments_rama_root ON inter_rama_assignments(other_rama_root_id);
CREATE INDEX idx_delegation_requests_delegator ON delegation_requests(delegator_id);