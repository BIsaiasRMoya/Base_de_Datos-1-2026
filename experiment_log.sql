-- ============================================================
-- Tabla de registro de experimentos (para documentar hallazgos)
-- No forma parte del modelo de gobernanza, es solo para el proyecto.
-- ============================================================

CREATE TABLE experiment_log (
    id SERIAL PRIMARY KEY,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version TEXT NOT NULL,                     -- 'v1', 'v2', 'v3', etc.
    script_name TEXT NOT NULL,                 -- 'simular_actividad.py'
    parameters JSONB NOT NULL,                 -- todos los argumentos usados
    total_invitations INTEGER,
    approved INTEGER,
    rejected INTEGER,
    total_votes INTEGER,
    avg_votes_per_invitation NUMERIC(5,2),
    approval_rate NUMERIC(5,2),                -- approved / total
    avg_neighborhood_size NUMERIC(5,2),
    notes TEXT                                  -- observaciones manuales (opcional)
);

COMMENT ON TABLE experiment_log IS 'Registro de ejecuciones de simulación para análisis posterior.';
COMMENT ON COLUMN experiment_log.parameters IS 'Objeto JSON con los argumentos de la ejecución (ej. {"num_invitaciones": 100, "prob_si": 0.6, ...}).';
COMMENT ON COLUMN experiment_log.notes IS 'Anotaciones libres del equipo sobre esta ejecución.';