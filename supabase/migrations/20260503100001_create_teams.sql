-- Organisation teams (one team per owner, many members)
CREATE TABLE IF NOT EXISTS ui.org_teams (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text        NOT NULL,
    owner_id    uuid        NOT NULL,
    invite_code text        NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ui.org_team_members (
    team_id   uuid        NOT NULL REFERENCES ui.org_teams(id) ON DELETE CASCADE,
    user_id   uuid        NOT NULL,
    role      text        NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member')),
    joined_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_org_team_members_user ON ui.org_team_members(user_id);

ALTER TABLE ui.org_teams        ENABLE ROW LEVEL SECURITY;
ALTER TABLE ui.org_team_members ENABLE ROW LEVEL SECURITY;

-- Team members can see their own team
CREATE POLICY "Team members read their team"
    ON ui.org_teams FOR SELECT
    USING (
        id IN (SELECT team_id FROM ui.org_team_members WHERE user_id = auth.uid())
    );

-- Only owner can update/delete
CREATE POLICY "Owner manages team"
    ON ui.org_teams FOR ALL
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

CREATE POLICY "Members read memberships"
    ON ui.org_team_members FOR SELECT
    USING (
        team_id IN (SELECT team_id FROM ui.org_team_members WHERE user_id = auth.uid())
    );

CREATE POLICY "Members manage own membership"
    ON ui.org_team_members FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
