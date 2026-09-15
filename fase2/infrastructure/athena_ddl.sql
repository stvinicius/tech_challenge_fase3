-- =============================================================================
-- Athena DDL -- registers the 3 Gold-layer tables in the AWS Glue Data
-- Catalog for querying via Amazon Athena.
--
-- Tables (written by pipelines/batch/build_gold.py to s3://<gold>/<table>/):
--   1. municipality_indicator  -- literacy percentage by municipality/year
--                                 (partitioned by year/state_code)
--   2. target_vs_result       -- actual result vs. target (municipality/state/national)
--                                 (partitioned by year/state_code)
--   3. time_evolution          -- aggregated historical series (national + state)
--                                 (single file, no partitioning)
--
-- The names used below (database, bucket) follow the defaults in
-- infrastructure/config.sh (PROJECT_NAME=brazil-literacy-pipeline). If you
-- ran setup_aws.sh with a custom PROJECT_NAME, replace:
--   - `brazil_literacy_pipeline` (database)      -> value of $GLUE_DATABASE
--   - `brazil-literacy-pipeline-gold` (S3 bucket) -> value of $GOLD_BUCKET
-- in the lines below before running this.
--
-- Partitioning via "partition projection": instead of MSCK REPAIR TABLE /
-- ALTER TABLE ... ADD PARTITION (which would require reprocessing the
-- catalog after every pipeline run), Athena computes the existing
-- partitions purely from the path pattern (Hive: year=<year>/state_code=<uf>/),
-- with no extra call to Glue needed. This is what build_gold.py/common.py
-- refer to as "Hive layout ... for partition projection in Athena".
--
-- How to run:
--   - Athena console: paste the content (one statement at a time, or the
--     newer multi-statement editor) using the workgroup created by
--     setup_aws.sh (${ATHENA_WORKGROUP}, e.g.: brazil-literacy-pipeline-wg);
--   - CLI:
--       aws athena start-query-execution \
--         --work-group "${ATHENA_WORKGROUP}" \
--         --query-string "$(cat infrastructure/athena_ddl.sql)"
--     (run the 4 statements individually if your CLI version doesn't accept
--     multiple statements separated by ';' in a single call).
--
-- Idempotent: every statement uses "IF NOT EXISTS", so they can be re-run
-- without errors.
-- =============================================================================

-- Glue database (already created by setup_aws.sh -- recreating it here is
-- just an idempotency safeguard in case this file is run on its own).
CREATE DATABASE IF NOT EXISTS brazil_literacy_pipeline
COMMENT 'Gold layer for the Child Literacy Indicator (Tech Challenge Phase 2)';

USE brazil_literacy_pipeline;

-- -----------------------------------------------------------------------------
-- 1. municipality_indicator
--    Literacy percentage by municipality/year, with the location attributes
--    (state, region) and the proficiency-level distribution
--    (proficiency_level_0..8_ratio). One row per municipality + year.
--    Written to s3://<gold>/municipality_indicator/year=<year>/state_code=<uf>/*.parquet
-- -----------------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS municipality_indicator (
    state_name                  STRING,
    region                      STRING,
    municipality_id              STRING,
    municipality_name            STRING,
    literacy_rate                DOUBLE,
    avg_portuguese_score         DOUBLE,
    source                       STRING,
    proficiency_level_0_ratio    DOUBLE,
    proficiency_level_1_ratio    DOUBLE,
    proficiency_level_2_ratio    DOUBLE,
    proficiency_level_3_ratio    DOUBLE,
    proficiency_level_4_ratio    DOUBLE,
    proficiency_level_5_ratio    DOUBLE,
    proficiency_level_6_ratio    DOUBLE,
    proficiency_level_7_ratio    DOUBLE,
    proficiency_level_8_ratio    DOUBLE
)
COMMENT 'Percentage of literate students by municipality and year (Gold)'
PARTITIONED BY (year INT, state_code STRING)
ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe'
STORED AS PARQUET
LOCATION 's3://brazil-literacy-pipeline-gold/municipality_indicator/'
TBLPROPERTIES (
    'projection.enabled' = 'true',
    'projection.year.type' = 'integer',
    'projection.year.range' = '2019,2035',
    'projection.state_code.type' = 'enum',
    'projection.state_code.values' = 'AC,AL,AP,AM,BA,CE,DF,ES,GO,MA,MT,MS,MG,PA,PB,PR,PE,PI,RJ,RN,RS,RO,RR,SC,SP,SE,TO',
    'storage.location.template' = 's3://brazil-literacy-pipeline-gold/municipality_indicator/year=${year}/state_code=${state_code}/'
);

-- -----------------------------------------------------------------------------
-- 2. target_vs_result
--    Compares the actual result (literacy_rate) with the target for the same
--    year at 3 levels (municipality, state, national), with the gap
--    (result - target) at each level. Years with no target defined (e.g.,
--    2023) end up with null target/gap.
--    Written to s3://<gold>/target_vs_result/year=<year>/state_code=<uf>/*.parquet
-- -----------------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS target_vs_result (
    state_name                   STRING,
    region                       STRING,
    municipality_id               STRING,
    municipality_name             STRING,
    literacy_rate                 DOUBLE,
    target_municipality           DOUBLE,
    gap_municipality               DOUBLE,
    target_state                  DOUBLE,
    gap_state                     DOUBLE,
    target_national                DOUBLE,
    gap_national                   DOUBLE,
    reached_target_municipality    BOOLEAN
)
COMMENT 'Actual result vs. National Commitment to Literate Children target, by municipality/state/national (Gold)'
PARTITIONED BY (year INT, state_code STRING)
ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe'
STORED AS PARQUET
LOCATION 's3://brazil-literacy-pipeline-gold/target_vs_result/'
TBLPROPERTIES (
    'projection.enabled' = 'true',
    'projection.year.type' = 'integer',
    'projection.year.range' = '2019,2035',
    'projection.state_code.type' = 'enum',
    'projection.state_code.values' = 'AC,AL,AP,AM,BA,CE,DF,ES,GO,MA,MT,MS,MG,PA,PB,PR,PE,PI,RJ,RN,RS,RO,RR,SC,SP,SE,TO',
    'storage.location.template' = 's3://brazil-literacy-pipeline-gold/target_vs_result/year=${year}/state_code=${state_code}/'
);

-- -----------------------------------------------------------------------------
-- 3. time_evolution
--    Historical series of the indicator aggregated by year, at the national
--    and state levels (average literacy rate + the corresponding
--    target/gap). Small table, written as a single Parquet file (no
--    partitioning): s3://<gold>/time_evolution/time_evolution.parquet
-- -----------------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS time_evolution (
    aggregation_level         STRING,
    year                      INT,
    state_code                STRING,
    state_name                STRING,
    region                    STRING,
    municipalities_assessed   BIGINT,
    avg_literacy_rate         DOUBLE,
    literacy_target           DOUBLE,
    gap                       DOUBLE
)
COMMENT 'Historical series of the indicator aggregated by year (national + state) (Gold)'
ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe'
STORED AS PARQUET
LOCATION 's3://brazil-literacy-pipeline-gold/time_evolution/';
