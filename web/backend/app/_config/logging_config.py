import logging
from .settings import settings


def setup_logger():
    # 确保日志目录存在
    log_path = settings.LOG_FILE
    log_dir = log_path.rsplit('/', 1)[0]
    if log_dir:
        import os
        os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(name)s:%(lineno)d] %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()  # 同时输出到控制台，方便调试
        ]
    )

