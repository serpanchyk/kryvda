CREATE TABLE monitored_channels (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_peer_id BIGINT UNIQUE,
    configured_reference TEXT NOT NULL UNIQUE,
    username TEXT,
    title TEXT,
    access_kind TEXT NOT NULL CHECK (access_kind IN ('public', 'private')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    last_collected_at TIMESTAMPTZ,
    last_error TEXT,
    last_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE collection_cursors (
    channel_id BIGINT PRIMARY KEY REFERENCES monitored_channels(id) ON DELETE CASCADE,
    latest_message_id BIGINT NOT NULL DEFAULT 0,
    backfill_before_message_id BIGINT,
    backfill_completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE raw_posts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id BIGINT NOT NULL REFERENCES monitored_channels(id),
    telegram_message_id BIGINT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    inaccessible_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, telegram_message_id)
);

CREATE TABLE post_revisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_post_id BIGINT NOT NULL REFERENCES raw_posts(id),
    revision_number INTEGER NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    edited_at TIMESTAMPTZ,
    attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (raw_post_id, revision_number)
);

CREATE TABLE analysis_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    post_revision_id BIGINT NOT NULL UNIQUE REFERENCES post_revisions(id),
    priority TEXT NOT NULL CHECK (priority IN ('live', 'backfill')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'leased', 'completed', 'failed')),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    leased_until TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX analysis_jobs_available_idx ON analysis_jobs (status, priority, available_at);
CREATE INDEX raw_posts_channel_published_idx ON raw_posts (channel_id, published_at DESC);

-- Populate this reviewed migration with the agreed channel list before first deployment.
