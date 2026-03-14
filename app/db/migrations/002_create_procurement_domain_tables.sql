CREATE TABLE IF NOT EXISTS manufacturers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS procurement_methods (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS purchase_names (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS units (
    id BIGSERIAL PRIMARY KEY,
    value TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS counterparties (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    inn TEXT,
    region TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT counterparties_inn_not_blank CHECK (inn IS NULL OR btrim(inn) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_counterparties_inn
    ON counterparties(inn)
    WHERE inn IS NOT NULL;

CREATE TABLE IF NOT EXISTS cte (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    category_id BIGINT NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    manufacturer_id BIGINT REFERENCES manufacturers(id) ON DELETE SET NULL,
    characteristics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cte_characteristics_object CHECK (jsonb_typeof(characteristics) = 'object')
);

CREATE TABLE IF NOT EXISTS contracts (
    id BIGINT PRIMARY KEY,
    purchase_name_id BIGINT NOT NULL REFERENCES purchase_names(id) ON DELETE RESTRICT,
    procurement_method_id BIGINT NOT NULL REFERENCES procurement_methods(id) ON DELETE RESTRICT,
    initial_price NUMERIC(18, 2) NOT NULL CHECK (initial_price >= 0),
    final_price NUMERIC(18, 2) NOT NULL CHECK (final_price >= 0),
    reduction_percent NUMERIC(18, 6) NOT NULL,
    vat_rate NUMERIC(5, 2) NOT NULL CHECK (vat_rate BETWEEN 0 AND 100),
    signed_at DATE NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES counterparties(id) ON DELETE RESTRICT,
    supplier_id BIGINT NOT NULL REFERENCES counterparties(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contract_items (
    id BIGSERIAL PRIMARY KEY,
    contract_id BIGINT NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    cte_id BIGINT NOT NULL REFERENCES cte(id) ON DELETE RESTRICT,
    quantity NUMERIC(18, 3) NOT NULL CHECK (quantity >= 0),
    unit_id BIGINT NOT NULL REFERENCES units(id) ON DELETE RESTRICT,
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cte_category_id ON cte(category_id);
CREATE INDEX IF NOT EXISTS idx_cte_manufacturer_id ON cte(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_cte_characteristics ON cte USING GIN(characteristics);

CREATE INDEX IF NOT EXISTS idx_contracts_purchase_name_id ON contracts(purchase_name_id);
CREATE INDEX IF NOT EXISTS idx_contracts_procurement_method_id ON contracts(procurement_method_id);
CREATE INDEX IF NOT EXISTS idx_contracts_customer_id ON contracts(customer_id);
CREATE INDEX IF NOT EXISTS idx_contracts_supplier_id ON contracts(supplier_id);
CREATE INDEX IF NOT EXISTS idx_contracts_signed_at ON contracts(signed_at);

CREATE INDEX IF NOT EXISTS idx_contract_items_contract_id ON contract_items(contract_id);
CREATE INDEX IF NOT EXISTS idx_contract_items_cte_id ON contract_items(cte_id);
CREATE INDEX IF NOT EXISTS idx_contract_items_unit_id ON contract_items(unit_id);
