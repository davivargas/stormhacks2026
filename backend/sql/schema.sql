-- PlasticPaths educational retrieval schema.
-- Run this explicitly against TiDB before seeding. The application never runs migrations.
-- The VECTOR dimension must match EMBEDDING_DIMENSIONS (default: 768).
CREATE TABLE IF NOT EXISTS educational_passages (
    document_id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    passage TEXT NOT NULL,
    source_url VARCHAR(1024) NOT NULL,
    tags JSON NOT NULL,
    embedding_model VARCHAR(128) NOT NULL,
    embedding_dimensions INT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    VECTOR INDEX idx_educational_passages_embedding
        ((VEC_COSINE_DISTANCE(embedding))) USING HNSW
);
