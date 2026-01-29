import requests
import pickle
from pathlib import Path
import os


def get_data_init():
    # response = requests.get(
    #     url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    # )
    # json_response = response.json()
    with open(Path(os.environ['appDir']) / "data_set/data_set.pkl", "rb", ) as f:
        json_response = pickle.load(f)
    # 解析数据
    return json_response


get_data_init_set = get_data_init()
