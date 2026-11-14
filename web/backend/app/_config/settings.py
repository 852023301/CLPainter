import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 加载 .env 文件（系统环境变量比 .env 文件优先级高）
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)  # 加载入 os.environ 但不覆写环境变量

DEFAULT_DATA_ROOT = Path("/mnt/DataDepartmentTest/home/wjl/data_set_dev")


class Settings(BaseSettings):
    """应用配置管理"""

    # 运行环境
    APP_ENV: str = os.getenv("APP_ENV", "development")
    SERVICE_NAME: str = os.getenv("SERVICE_NAME", "clpainter-local")

    # 项目路径配置
    PRJ_DIR: str = os.getenv("PRJ_DIR", "/root/CLPainter")
    APP_DIR: str = os.getenv("APP_DIR", "/root/CLPainter/web/backend/app")

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    LOG_FILE: str = os.getenv("LOG_FILE", "/app/logs/app.log")

    # 数据存储路径
    DATA_DIR: str = os.getenv("DATA_DIR", str(DEFAULT_DATA_ROOT / "pv_data"))
    OLD_DATA_DIR: str = os.getenv("OLD_DATA_DIR", str(DEFAULT_DATA_ROOT / "old_pv_data"))
    CACHE_DUMP_DIR: str = os.getenv("CACHE_DUMP_DIR", str(DEFAULT_DATA_ROOT / "dump" / "curated"))
    DB_PATH: str = os.getenv("DB_PATH", str(DEFAULT_DATA_ROOT / "instrument.db"))

    # Phase 7 实验开关
    ENABLE_XIANDUAN_REPAIR_LOOP: bool = os.getenv(
        "ENABLE_XIANDUAN_REPAIR_LOOP", "0"
    ).lower() in {"1", "true", "yes", "on"}
    ENABLE_XIANDUAN_LOCAL_RESEGMENT: bool = os.getenv(
        "ENABLE_XIANDUAN_LOCAL_RESEGMENT", "0"
    ).lower() in {"1", "true", "yes", "on"}
    ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH: bool = os.getenv(
        "ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH", "0"
    ).lower() in {"1", "true", "yes", "on"}

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


def validate_settings(config: Settings) -> None:
    """启动时校验环境与数据目录，避免正式和测试服务互相串数据。"""
    app_env = config.APP_ENV.strip().lower()
    if app_env not in {"development", "production", "test"}:
        raise RuntimeError(f"不支持的 APP_ENV: {config.APP_ENV}")

    data_root = Path(config.DATA_DIR).parent
    data_paths = {
        "DATA_DIR": Path(config.DATA_DIR),
        "OLD_DATA_DIR": Path(config.OLD_DATA_DIR),
        "CACHE_DUMP_DIR": Path(config.CACHE_DUMP_DIR),
        "DB_PATH": Path(config.DB_PATH),
    }

    if app_env == "production" and data_root.name != "data_set":
        raise RuntimeError("production 必须使用生产数据目录 data_set")
    if app_env == "test" and data_root.name != "data_set_dev":
        raise RuntimeError("test 必须使用测试数据目录 data_set_dev")

    for name, path in data_paths.items():
        if path != data_root and data_root not in path.parents:
            raise RuntimeError(
                f"{name} 必须位于同一数据根目录 {data_root} 下: {path}"
            )


settings = Settings()
validate_settings(settings)
