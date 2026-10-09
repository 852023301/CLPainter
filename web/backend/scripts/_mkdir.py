from itertools import product
from pathlib import Path
import subprocess
from CLPainter.web.backend.app._config.settings import settings

BASE_DIR = Path(settings.DATA_DIR)

FREQ_LIST = [
    "freq=1min", "freq=5min", "freq=15min", "freq=30min",
    "freq=60min", "freq=120min", "freq=240min", "freq=1day",
    "freq=1week", "freq=1month", "freq=1year",
]
MARKETS = ["market=cn"]
ASSET_CLASSES = ["asset_class=stock"]

for freq, market, asset_class in product(FREQ_LIST, MARKETS, ASSET_CLASSES):
    target_dir = BASE_DIR / freq / market / asset_class
    target_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["chmod", "-R", "777", target_dir], check=True)
    print(f"已递归设置 777: {target_dir}")