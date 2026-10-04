-- Street names. add_street_names.py (db/) fills these; the columns exist already on the live database.
ALTER TABLE streets  ADD COLUMN IF NOT EXISTS name text;
ALTER TABLE manholes ADD COLUMN IF NOT EXISTS place_name text;
