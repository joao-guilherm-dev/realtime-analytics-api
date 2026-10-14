import logging
import time

from .alerts import AlertEngine
from .config import DEFAULT_SECRET, settings
from .database import Database
from .hub import StreamHub
from .security import hash_password

log = logging.getLogger("rtapi")


class AppState:
    """Estado global da aplicação (banco, hub em memória, alertas, contadores)."""

    def __init__(self) -> None:
        self.db = Database(settings.db_path)
        self.hub = StreamHub(settings.buffer_size)
        self.alerts = AlertEngine()
        self.started_at = time.time()
        self.counters = {"points_ingested": 0, "anomalies": 0, "alerts_fired": 0}
        self.ws_connections = 0

    def start(self) -> None:
        self.started_at = time.time()
        self.db.init()
        for m in self.db.metric_names():
            self.hub.load(m, self.db.recent_points(m, settings.buffer_size))
        self.alerts.load(self.db.list_rules())
        if settings.secret_key == DEFAULT_SECRET:
            log.warning("SECRET_KEY padrão em uso — defina uma chave própria em produção!")
        if settings.admin_user and settings.admin_password and not self.db.get_user(settings.admin_user):
            self.db.create_user(settings.admin_user, hash_password(settings.admin_password))
            log.info("Usuário admin '%s' criado", settings.admin_user)

    def stop(self) -> None:
        self.db.close()


state = AppState()
