-- ============================================================
-- v3 — Registro del perfil del candidato en la invitación
-- Migración ADITIVA sobre v2: agrega columnas a la tabla invitations.
-- ============================================================

-- Añadir columnas para el perfil del candidato simulado
ALTER TABLE invitations ADD COLUMN candidate_socioeconomic_level TEXT;
ALTER TABLE invitations ADD COLUMN candidate_backgrounds TEXT[];

COMMENT ON COLUMN invitations.candidate_socioeconomic_level IS 'Nivel socioeconómico asignado al candidato en el momento de la simulación (v2/v3).';
COMMENT ON COLUMN invitations.candidate_backgrounds IS 'Arreglo con los tipos de antecedentes simulados del candidato (ej. {"judicial", "laboral"}).';

-- Índice opcional para consultas frecuentes sobre antecedentes judiciales
CREATE INDEX idx_invitations_candidate_backgrounds ON invitations USING GIN (candidate_backgrounds);