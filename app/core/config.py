from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TenderHackPerm API"
    app_version: str = "0.1.0"
    app_env: str = "dev"
    api_v1_prefix: str = "/api/v1"

    postgres_db: str = Field(default="tenderhackperm", alias="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_min_pool_size: int = Field(default=1, alias="POSTGRES_MIN_POOL_SIZE")
    postgres_max_pool_size: int = Field(default=10, alias="POSTGRES_MAX_POOL_SIZE")
    postgres_ssl_mode: str = Field(default="disable", alias="POSTGRES_SSL_MODE")
    import_data_dir: str = Field(default="data/imports", alias="IMPORT_DATA_DIR")
    import_cte_filename: str = Field(default="cte.xlsx", alias="IMPORT_CTE_FILENAME")
    import_contracts_filename: str = Field(default="contracts.xlsx", alias="IMPORT_CONTRACTS_FILENAME")
    embeddings_model_name: str = Field(default="intfloat/multilingual-e5-small", alias="EMBEDDINGS_MODEL_NAME")
    embeddings_dimensions: int = Field(default=384, alias="EMBEDDINGS_DIMENSIONS")
    embeddings_batch_size: int = Field(default=16, alias="EMBEDDINGS_BATCH_SIZE")
    embeddings_max_length: int = Field(default=512, alias="EMBEDDINGS_MAX_LENGTH")
    embeddings_document_prefix: str = Field(default="passage: ", alias="EMBEDDINGS_DOCUMENT_PREFIX")
    embeddings_query_prefix: str = Field(default="query: ", alias="EMBEDDINGS_QUERY_PREFIX")
    geopy_user_agent: str = Field(default="tenderhackperm", alias="GEOPY_USER_AGENT")
    geopy_timeout_seconds: int = Field(default=10, alias="GEOPY_TIMEOUT_SECONDS")
    analytics_category_only_multiplier: float = Field(
        default=0.65,
        alias="ANALYTICS_CATEGORY_ONLY_MULTIPLIER",
    )
    analytics_fallback_multiplier: float = Field(default=0.2, alias="ANALYTICS_FALLBACK_MULTIPLIER")
    analytics_geo_decay_km: float = Field(default=1500.0, alias="ANALYTICS_GEO_DECAY_KM")
    analytics_moscow_spb_penalty: float = Field(default=0.7, alias="ANALYTICS_MOSCOW_SPB_PENALTY")
    analytics_remote_penalty: float = Field(default=0.55, alias="ANALYTICS_REMOTE_PENALTY")
    analytics_kaliningrad_penalty: float = Field(default=0.8, alias="ANALYTICS_KALININGRAD_PENALTY")
    analytics_time_half_life_days: float = Field(default=365.0, alias="ANALYTICS_TIME_HALF_LIFE_DAYS")
    analytics_iqr_multiplier: float = Field(default=1.5, alias="ANALYTICS_IQR_MULTIPLIER")
    analytics_missing_embedding_weight: float = Field(
        default=0.35,
        alias="ANALYTICS_MISSING_EMBEDDING_WEIGHT",
    )
    analytics_vector_limit: int = Field(default=250, alias="ANALYTICS_VECTOR_LIMIT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
