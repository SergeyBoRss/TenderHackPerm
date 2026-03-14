ALTER TABLE contracts
    DROP CONSTRAINT IF EXISTS contracts_reduction_percent_check;

ALTER TABLE contracts
    ALTER COLUMN reduction_percent TYPE NUMERIC(18, 6);
