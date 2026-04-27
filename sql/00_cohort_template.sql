-- Cohort extraction template
-- Replace source tables with harmonized silver/gold datasets.

CREATE OR REPLACE TABLE cohort AS
SELECT *
FROM source_table
WHERE 1=1;
