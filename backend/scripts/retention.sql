-- Keep cached ocean currents from filling the Tiger free tier (750 MiB).
--
-- A 10-degree snapshot (the largest that is stored) is about 58,000 rows (~7 MB before compression), and every new
-- area-hour stores one. Snapshots are keyed by the hour, so a snapshot from a past hour is
-- never read again: dropping them after two days loses nothing the app uses.
-- Runs (the positions table) are NOT affected.
--
-- Apply once from the Tiger console SQL editor. This DELETES cached currents older than
-- two days, including any test rows from earlier hours.

-- Smaller chunks so whole days can be dropped (applies to chunks created from now on).
SELECT set_chunk_time_interval('current_samples', INTERVAL '1 day');

SELECT add_retention_policy('current_samples', INTERVAL '2 days', if_not_exists => TRUE);
