-- goku-router v1.5.32 schema patch (run separately against QA and Prod)
-- Execute with a DBA account. The application account intentionally has no ALTER privilege.
-- Existing telemetry rows are preserved; new columns are nullable where historical values
-- cannot be reconstructed reliably.
-- Before executing, check each target database and skip any ADD COLUMN / CREATE INDEX
-- statement whose column or index already exists.

ALTER TABLE prompt_cache_entries
  ADD COLUMN cache_purged_20260802 BOOLEAN NOT NULL DEFAULT 1;

ALTER TABLE providers
  ADD COLUMN avg_output_tokens_per_sec FLOAT NULL;

ALTER TABLE request_logs
  ADD COLUMN provider_id INT NULL,
  ADD COLUMN created_at DATETIME NULL;

ALTER TABLE provider_quality_scores
  ADD COLUMN provider_id INT NULL;

CREATE INDEX ix_request_logs_provider_id
  ON request_logs (provider_id);

CREATE INDEX ix_request_logs_created_at
  ON request_logs (created_at);

CREATE INDEX ix_provider_quality_scores_provider_id
  ON provider_quality_scores (provider_id);

-- Verification: each SHOW must return exactly one row.
SHOW COLUMNS FROM prompt_cache_entries LIKE 'cache_purged_20260802';
SHOW COLUMNS FROM providers LIKE 'avg_output_tokens_per_sec';
SHOW COLUMNS FROM request_logs LIKE 'provider_id';
SHOW COLUMNS FROM request_logs LIKE 'created_at';
SHOW COLUMNS FROM provider_quality_scores LIKE 'provider_id';

SHOW INDEX FROM request_logs WHERE Key_name IN (
  'ix_request_logs_provider_id',
  'ix_request_logs_created_at'
);
SHOW INDEX FROM provider_quality_scores
  WHERE Key_name = 'ix_provider_quality_scores_provider_id';
