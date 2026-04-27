-- Template: data dictionary extraction (DB-dependent functions may vary)
SELECT
  column_name,
  data_type
FROM information_schema.columns
WHERE table_name = 'analysis_table';
