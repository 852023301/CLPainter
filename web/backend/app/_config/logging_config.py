import logging


def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s:%(lineno)d] %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("/app/logs/app.log", encoding='utf-8'), ]
    )

