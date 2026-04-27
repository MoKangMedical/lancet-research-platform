-- Template: build analysis-ready table from harmonized source.
CREATE OR REPLACE TABLE analysis_table AS
SELECT *
FROM source_table
WHERE 1 = 1;
