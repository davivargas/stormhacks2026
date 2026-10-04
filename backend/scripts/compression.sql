ALTER TABLE positions SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'run_id',
  timescaledb.compress_orderby = 'time'
);
SELECT add_compression_policy('positions', INTERVAL '1 day', if_not_exists => TRUE);

ALTER TABLE current_samples SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'snapshot_id',
  timescaledb.compress_orderby = 'time'
);
SELECT add_compression_policy('current_samples', INTERVAL '1 day', if_not_exists => TRUE);
