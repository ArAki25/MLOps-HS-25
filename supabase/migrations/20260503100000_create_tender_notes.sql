-- Tender notes: one note per user per simap project
CREATE TABLE IF NOT EXISTS ui.user_tender_notes (
    user_id    uuid        NOT NULL,
    simap_id   text        NOT NULL,
    note       text        NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, simap_id)
);

-- Allow authenticated users to manage only their own notes
ALTER TABLE ui.user_tender_notes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own tender notes"
    ON ui.user_tender_notes
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
