CREATE TABLE monitored_channels (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_peer_id BIGINT UNIQUE,
    configured_reference TEXT NOT NULL UNIQUE,
    username TEXT,
    title TEXT,
    avatar_url TEXT,
    avatar_content_type TEXT,
    avatar_updated_at TIMESTAMPTZ,
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

CREATE INDEX raw_posts_channel_published_idx ON raw_posts (channel_id, published_at DESC);

INSERT INTO monitored_channels (configured_reference, username, title, access_kind)
VALUES
    ('insiderUKR', 'insiderUKR', 'INSIDER UA', 'public'),
    ('u_now', 'u_now', 'Україна Сейчас', 'public'),
    ('voynareal', 'voynareal', 'Реальна війна', 'public'),
    ('UaOnlii', 'UaOnlii', 'Україна Online', 'public'),
    ('times_ukraina', 'times_ukraina', 'Times of Ukraine', 'public')
ON CONFLICT (configured_reference) DO UPDATE
SET username = EXCLUDED.username,
    title = EXCLUDED.title,
    access_kind = EXCLUDED.access_kind,
    updated_at = now();
