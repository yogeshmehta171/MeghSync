-- "Measures taken": free text an official records against a citizen report (what was done about it).
ALTER TABLE reports ADD COLUMN IF NOT EXISTS measures    text;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS measures_by text;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS measures_at timestamptz;
