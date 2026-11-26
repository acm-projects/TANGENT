-- What each tag colour means in a case ({color: label}); NULL means the defaults (schemas.DEFAULT_TAG_LABELS).
ALTER TABLE projects ADD COLUMN IF NOT EXISTS tag_labels JSONB;
