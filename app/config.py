import os


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


DEFAULT_SECRET = "dev-secret-troque-em-producao-0123456789"


class Settings:
    """Configuração lida de variáveis de ambiente (12-factor)."""

    def __init__(self) -> None:
        self.app_name = "Realtime Analytics API"
        self.version = "1.0.0"
        self.secret_key = os.getenv("SECRET_KEY", DEFAULT_SECRET)
        self.algorithm = "HS256"
        self.token_expire_minutes = int(os.getenv("TOKEN_EXPIRE_MINUTES", "60"))
        self.pbkdf2_iterations = int(os.getenv("PBKDF2_ITERATIONS", "200000"))
        self.db_path = os.getenv("DB_PATH", "data/analytics.db")
        self.buffer_size = int(os.getenv("BUFFER_SIZE", "5000"))
        self.retention_days = int(os.getenv("RETENTION_DAYS", "30"))
        self.rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "600"))
        self.allow_registration = _bool("ALLOW_REGISTRATION", True)
        self.admin_user = os.getenv("ADMIN_USER", "")
        self.admin_password = os.getenv("ADMIN_PASSWORD", "")
        self.cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]


settings = Settings()
