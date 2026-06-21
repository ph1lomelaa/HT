import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Позволяет использовать обычный файл .env при локальном запуске.
# Переменные окружения сервера имеют приоритет над значениями из файла.
load_dotenv(REPOSITORY_ROOT / ".env")


@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    google_creds: str | None
    project_root: Path
    tmp_dir: Path
    assets_dir: Path
    credentials_file: Path

    @classmethod
    def from_env(cls) -> "AppConfig":
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError(
                "Не задан BOT_TOKEN. Добавьте его в файл .env или переменные окружения."
            )

        return cls(
            bot_token=bot_token,
            google_creds=os.getenv("GOOGLE_CREDS"),
            project_root=PROJECT_ROOT,
            tmp_dir=PROJECT_ROOT / "tmp",
            assets_dir=PROJECT_ROOT / "assets",
            credentials_file=(
                PROJECT_ROOT
                / "credentials"
                / "service_account.json"
            ),
        )


config = AppConfig.from_env()
config.tmp_dir.mkdir(parents=True, exist_ok=True)
