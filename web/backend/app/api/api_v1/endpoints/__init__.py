import requests

def get_data_init():
    response = requests.get(
        url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    )
    json_response = response.json()
    # 解析数据
    return json_response


get_data_init_set = get_data_init()