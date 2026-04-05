-- =============================================================================
-- Multi-Agent AI Platform — Reference SQL Schema
-- Generated from ORM models. Use Alembic for actual migrations.
-- Engine: PostgreSQL 15+
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- optional: fuzzy text search

-- =============================================================================
-- ENUM types
-- =============================================================================

CREATE TYPE document_status_enum AS ENUM (
    'uploaded',
    'processing',
    'ready',
    'failed'
);

CREATE TYPE kb_status_enum AS ENUM (
    'active',
    'inactive'
);

CREATE TYPE message_role_enum AS ENUM (
    'user',
    'assistant',
    'system'
);

-- =============================================================================
-- users
-- =============================================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       INTEGER NOT NULL DEFAULT 1,
    email           VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(512) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX ix_users_tenant_email ON users (tenant_id, email);

-- =============================================================================
-- agents
-- =============================================================================

CREATE TABLE agents (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id           INTEGER NOT NULL DEFAULT 1,
    name                VARCHAR(255) NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    topic               VARCHAR(255) NOT NULL,
    system_prompt       TEXT NOT NULL,

    -- Pinecone — format: tenant_{tid}_user{uid}_agent{aid}
    pinecone_namespace  VARCHAR(512) NOT NULL,

    -- Model configuration
    embedding_model     VARCHAR(255) NOT NULL DEFAULT 'text-embedding-004',
    llm_model           VARCHAR(255) NOT NULL DEFAULT 'anthropic.claude-3-5-sonnet-20241022-v2:0',
    llm_temperature     FLOAT NOT NULL DEFAULT 0.1,
    llm_max_tokens      INTEGER NOT NULL DEFAULT 4096,

    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_agents_namespace UNIQUE (pinecone_namespace)
);

CREATE INDEX ix_agents_user_id ON agents (user_id);
CREATE INDEX ix_agents_tenant_active ON agents (tenant_id, is_active);

-- =============================================================================
-- knowledge_bases
-- =============================================================================

CREATE TABLE knowledge_bases (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id            UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,

    pinecone_index      VARCHAR(255) NOT NULL,           -- shared index name
    pinecone_namespace  VARCHAR(512) NOT NULL,           -- unique per agent
    embedding_model     VARCHAR(255) NOT NULL,
    embedding_dimension INTEGER NOT NULL DEFAULT 3072,

    status              kb_status_enum NOT NULL DEFAULT 'active',
    total_documents     INTEGER NOT NULL DEFAULT 0,
    total_chunks        INTEGER NOT NULL DEFAULT 0,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_kb_agent UNIQUE (agent_id),
    CONSTRAINT uq_kb_namespace UNIQUE (pinecone_namespace)
);

CREATE INDEX ix_kb_agent_id ON knowledge_bases (agent_id);

-- =============================================================================
-- documents
-- =============================================================================

CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id        UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,

    file_name       VARCHAR(512) NOT NULL,
    mime_type       VARCHAR(128) NOT NULL,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    storage_path    VARCHAR(1024) NOT NULL,      -- S3 key
    storage_bucket  VARCHAR(255) NOT NULL,

    status          document_status_enum NOT NULL DEFAULT 'uploaded',
    error_message   TEXT,

    -- Processing metadata
    total_chunks    INTEGER NOT NULL DEFAULT 0,
    embedding_model VARCHAR(255) NOT NULL DEFAULT '',
    chunk_size      INTEGER NOT NULL DEFAULT 1000,
    chunk_overlap   INTEGER NOT NULL DEFAULT 200,

    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

CREATE INDEX ix_documents_agent_id ON documents (agent_id);
CREATE INDEX ix_documents_user_id  ON documents (user_id);
CREATE INDEX ix_documents_status   ON documents (status);

-- =============================================================================
-- document_chunks
-- =============================================================================

CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    agent_id        UUID NOT NULL,              -- denormalized for fast namespace lookups

    chunk_index     INTEGER NOT NULL,
    vector_id       VARCHAR(512) NOT NULL,      -- Pinecone vector ID
    text_preview    VARCHAR(512) NOT NULL DEFAULT '',
    page_from       INTEGER,
    page_to         INTEGER,
    token_count     INTEGER NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_chunk_vector UNIQUE (vector_id),
    CONSTRAINT uq_chunk_doc_index UNIQUE (document_id, chunk_index)
);

CREATE INDEX ix_chunks_document_id ON document_chunks (document_id);
CREATE INDEX ix_chunks_agent_id    ON document_chunks (agent_id);

-- =============================================================================
-- chat_sessions
-- =============================================================================

CREATE TABLE chat_sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id    UUID REFERENCES agents(id) ON DELETE SET NULL,

    title       VARCHAR(512) NOT NULL DEFAULT 'New Chat',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_sessions_user_id  ON chat_sessions (user_id);
CREATE INDEX ix_sessions_agent_id ON chat_sessions (agent_id);

-- =============================================================================
-- chat_messages
-- =============================================================================

CREATE TABLE chat_messages (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role                message_role_enum NOT NULL,
    content             TEXT NOT NULL,

    -- Agent that handled this turn (assistant only)
    agent_id            UUID,
    agent_name          VARCHAR(255),

    -- RAG sources as JSONB array:
    --   [{document_id, filename, chunk_index, page_from, page_to, score}]
    sources_json        JSONB,

    -- LLM token usage
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_messages_session_id ON chat_messages (session_id);
CREATE INDEX ix_messages_role       ON chat_messages (role);

-- =============================================================================
-- Trigger: auto-update updated_at columns
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_agents_updated_at
    BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_kb_updated_at
    BEFORE UPDATE ON knowledge_bases
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
