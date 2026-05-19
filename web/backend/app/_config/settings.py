import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载 .env 文件（系统环境变量比.env文件优先级高）
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)  # 加载入 os.environ但 不覆写环境变量


class Settings(BaseSettings):
    """应用配置管理"""
    
    # 项目路径配置
    PRJ_DIR: str = os.getenv("PRJ_DIR", "/root/CLPainter")
    APP_DIR: str = os.getenv("APP_DIR", "/root/CLPainter/web/backend/app")

    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    LOG_FILE: str = os.getenv("LOG_FILE", "/app/logs/app.log")


    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
