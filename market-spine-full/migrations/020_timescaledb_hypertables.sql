-- Enable TimescaleDB extension (optional)
-- This migration converts time-series tables to hypertables for better performance
-- If TimescaleDB is not installed, this migration will be skipped gracefully

-- Check if TimescaleDB is available before attempting to enable it
DO $$
BEGIN
    -- Try to create the extension
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
    RAISE NOTICE 'TimescaleDB extension enabled successfully';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'TimescaleDB not available, skipping hypertable creation. Error: %', SQLERRM;
END $$;

-- Only create hypertables if TimescaleDB is enabled
DO $$
DECLARE
    timescale_enabled BOOLEAN;
BEGIN
    -- Check if timescaledb extension exists
    SELECT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
    ) INTO timescale_enabled;
    
    IF NOT timescale_enabled THEN
        RAISE NOTICE 'TimescaleDB not enabled, skipping hypertable configuration';
        RETURN;
    END IF;
    
    -- Convert otc_trades_raw to hypertable (partition by ingested_at)
    PERFORM create_hypertable(
        'otc_trades_raw',
        'ingested_at',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE,
        migrate_data => TRUE
    );
    RAISE NOTICE 'Created hypertable: otc_trades_raw';
    
    -- Convert otc_trades to hypertable (partition by trade_date)
    PERFORM create_hypertable(
        'otc_trades',
        'trade_date',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE,
        migrate_data => TRUE
    );
    RAISE NOTICE 'Created hypertable: otc_trades';
    
    -- Convert otc_metrics_daily to hypertable (partition by date)
    PERFORM create_hypertable(
        'otc_metrics_daily',
        'date',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE,
        migrate_data => TRUE
    );
    RAISE NOTICE 'Created hypertable: otc_metrics_daily';
    
    -- Enable compression on older chunks
    ALTER TABLE otc_trades_raw SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'source',
        timescaledb.compress_orderby = 'ingested_at DESC'
    );
    
    ALTER TABLE otc_trades SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'symbol',
        timescaledb.compress_orderby = 'trade_date DESC'
    );
    
    ALTER TABLE otc_metrics_daily SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'symbol',
        timescaledb.compress_orderby = 'date DESC'
    );
    
    -- Add compression policies (compress chunks older than 7 days)
    PERFORM add_compression_policy('otc_trades_raw', INTERVAL '7 days', if_not_exists => TRUE);
    PERFORM add_compression_policy('otc_trades', INTERVAL '7 days', if_not_exists => TRUE);
    PERFORM add_compression_policy('otc_metrics_daily', INTERVAL '30 days', if_not_exists => TRUE);
    
    RAISE NOTICE 'TimescaleDB compression policies configured';
    
END $$;
