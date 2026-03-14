DROP INDEX IF EXISTS idx_cte_embeddings_embedding_cosine;

TRUNCATE TABLE cte_embeddings RESTART IDENTITY;

ALTER TABLE cte_embeddings
    ALTER COLUMN embedding TYPE VECTOR(384);

CREATE INDEX IF NOT EXISTS idx_cte_embeddings_embedding_cosine
    ON cte_embeddings
    USING hnsw (embedding vector_cosine_ops);
