-- Re-read each channel's one-year backfill window over the next hourly collection runs.
-- Stored posts receive current Telegram metadata (for example the forward origin); a changed
-- text becomes a new revision and is analyzed, unchanged posts are left as they are.
UPDATE collection_cursors
SET backfill_before_message_id = NULL,
    backfill_completed_at = NULL,
    updated_at = now();
