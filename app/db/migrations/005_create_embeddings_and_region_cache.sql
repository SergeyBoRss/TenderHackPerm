CREATE TABLE IF NOT EXISTS region_geo_cache (
    region TEXT PRIMARY KEY,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geocoder_source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cte_embeddings (
    id BIGSERIAL PRIMARY KEY,
    cte_id BIGINT NOT NULL UNIQUE REFERENCES cte(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL CHECK (embedding_dimensions > 0),
    input_text TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cte_embeddings_model_name ON cte_embeddings(model_name);
CREATE INDEX IF NOT EXISTS idx_cte_embeddings_input_hash ON cte_embeddings(input_hash);
CREATE INDEX IF NOT EXISTS idx_cte_embeddings_embedding_cosine
    ON cte_embeddings
    USING hnsw (embedding vector_cosine_ops);
