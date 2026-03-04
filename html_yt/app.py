from flask import Flask
from flask import Flask, render_template
import numpy as np
import requests
import os
import pandas as pd
import dateutil.parser
import pytz
import joblib
from datetime import datetime, timedelta, timezone
from tensorflow.keras.models import load_model
from typing import Optional,Dict,List,Tuple
from dotenv import load_dotenv

load_dotenv()

METRIS_URI = os.getenv('METRIS_URI')
METRIS_USERNAME = os.getenv('METRIS_USERNAME')
METRIS_PASSWORD = os.getenv('METRIS_PASSWORD')

app = Flask(__name__)

def get_metris_token():
    auth_data = {"username": METRIS_USERNAME, "password": METRIS_PASSWORD}
    auth_uri = f"{METRIS_URI}/api/account/authenticate"
    response = requests.post(auth_uri, json=auth_data, verify=False)  
    token_data = response.json()  
    token = token_data.get("id") 
    headers = {"Authorization": f"Bearer {token}"}  
    return {"base_url": METRIS_URI}, token, headers

def get_tag_values(ids):
    try:
        metris_info, token, headers = get_metris_token()
        url = f"{metris_info['base_url']}/api/historian/v02/tagvalues"
        params = {'ids': ids}
        
        response = requests.get(
            url, 
            headers=headers, 
            params=params, 
            verify=False  
        )
        
        if response.status_code != 200:
            raise Exception(f"API请求失败: {response.status_code}")
            
        result = response.json()
        if not isinstance(result, list):
            raise Exception("API返回格式错误")
        return {item['tagID']: item['value'] for item in result}
        
    except Exception as e:
        print(f"获取tag值失败: {str(e)}")
        return {id: 50 + np.random.rand() * 50 for id in ids}
    
tzwl = pytz.timezone("Asia/Shanghai")

def fix_tag_value(value: dict) -> dict:
    return {
        'value': 0.0,
        'valueLast': 0.0,
        **value
    }

def fix_tag_values(values: list) -> list:
    values = [fix_tag_value(tv) for tv in values]
    for d in values:
        d.update((k, dateutil.parser.isoparse(v).astimezone(tzwl).isoformat()) for k, v in d.items() if ((k == "timestamp") or (k == "timestampLast")))
    return values

def fix_trend_value(value: dict) -> dict:
    if 't' in value:
        value['x'] = value['t']
        del value['t']
    
    if 'v' in value:
        value['y'] = value['v']
        del value['v']
    elif 'st' in value:
        value['y'] = value['st']
        del value['st']
        
    return {
        'y': 0.0,
        **value
    }

def fix_trend_values(values: list) -> list:
    values = [fix_trend_value(v) for v in values]
    for d in values:
        d.update((k, datetime.fromtimestamp(v / 1000).isoformat()) for k, v in d.items() if k == "x")
    values = sorted(values, key=lambda v: v['x'])
    return values

def get_trend_values(ids, number_days=7):
    metris_info, token, headers = get_metris_token()  
    METRIS_URI = metris_info["base_url"]
    result = {}

    for tag_id in ids:
        now = datetime.now()
        end_time = datetime(now.year, now.month, now.day) - timedelta(seconds=1)
        start_time = end_time - timedelta(days=number_days - 1)

        trend_params = {
            'tagid': tag_id,
            'start': start_time.isoformat(),
            'end': end_time.isoformat(),
            'timeshift': 0,
            'interpolationmethod': 1,
            'interpolationresolution': 0,
            'interpolationresolutiontype': 0,
            'aggregatefunction': 0,
            'trackingreferencestep': None
        }

        trend_uri = f'{METRIS_URI}/api/historian/v02/trendvalues'
        response = requests.get(trend_uri, headers=headers, params=trend_params, verify=False)

        if response.status_code == 200:
            try:
                raw_data = fix_trend_values(response.json())

                daily_data = {}
                for point in raw_data:
                    ts = datetime.fromisoformat(point['x'])
                    day_key = ts.date()
                    target_time = datetime.combine(day_key, datetime.min.time()) + timedelta(hours=12)
                    diff = abs((ts - target_time).total_seconds())

                    if day_key not in daily_data or diff < daily_data[day_key]['diff']:
                        daily_data[day_key] = {'point': point, 'diff': diff}

                sorted_days = sorted(daily_data.keys())
                result[tag_id] = [daily_data[day]['point'] for day in sorted_days]
            except Exception as e:
                print("解析 JSON 失败：", e)
                result[tag_id] = {'error': 'Invalid JSON'}
        else:
            result[tag_id] = {'error': f"Failed to retrieve data for tag_id {tag_id}"}

    return result


def dict_to_timeseries_df(raw_dict, tag_name_map=None, resample_freq=None):
    series_list = []
    col_names = []

    for key, lst in raw_dict.items():
        if not lst:
            continue
        df = pd.DataFrame(lst)
        df['x'] = pd.to_datetime(df['x'])
        df = df.sort_values('x').drop_duplicates(subset='x', keep='last')
        df = df.set_index('x').sort_index()
        s = df['y'].astype(float)
        series_list.append(s)
        col_name = tag_name_map.get(key, str(key)) if tag_name_map else str(key)
        col_names.append(col_name)

    if not series_list:
        raise ValueError("输入字典为空或不存在有效数据。")

    combined = pd.concat(series_list, axis=1)
    combined.columns = col_names

    combined = combined.sort_index().ffill().bfill()

    if resample_freq:
        combined = (combined
                    .resample(resample_freq)
                    .mean()
                    .interpolate('time')
                    .ffill()
                    .bfill())

    return combined

def predict_next_from_dict(
    raw_dict: Dict,
    model_path: str,
    scalerX_path: str,
    scalery_path: str,
    target_col_name: str,
    seq_len: Optional[int] = None,
    tag_name_map: Optional[Dict] = None,
    resample_freq: Optional[str] = None,
    to_tz: Optional[str] = "Asia/Shanghai"
) -> float:
  
    df = dict_to_timeseries_df(
        raw_dict=raw_dict,
        tag_name_map=tag_name_map,
        resample_freq=resample_freq,
        to_tz=to_tz
    )

    model = load_model(model_path)
    scaler_X = joblib.load(scalerX_path)
    scaler_y = joblib.load(scalery_path)

    if seq_len is None:
        seq_len = model.layers[0].input_shape[1]

    if target_col_name not in df.columns:
        raise ValueError(f"传入数据缺少目标列 {target_col_name}。现有列：{list(df.columns)}")

    feature_cols = [c for c in df.columns if c != target_col_name]
    if len(feature_cols) == 0:
        raise ValueError("没有可用特征列（除了目标列之外至少需要1列）。")

    if len(df) < seq_len:
        raise ValueError(f"数据长度 {len(df)} < 模型所需时间步 {seq_len}，请提供更多最近数据点。")

    latest_block = df[feature_cols].iloc[-seq_len:]
    X_input = scaler_X.transform(latest_block.values).reshape(1, seq_len, len(feature_cols))

    y_pred_scaled = model.predict(X_input, verbose=0)
    y_pred = scaler_y.inverse_transform(y_pred_scaled)[0, 0]
    return float(y_pred)

@app.route('/')
def index():
    return render_template('index.html')

# @app.route('/api/data')
# def get_data():
#     tag_ids = [11483,12071,749,748,11487,1270]
#     tag_values = get_tag_values(tag_ids,number_days=1)

#     result = get_trend_values[tag_ids]
#     tag_name_map = {787:"Brightness",
#                     11483:'Power',
#                     12071:'Consis_HCR1_SS',
#                     749:'Temperature',
#                     748:'lever',
#                     11487:'tower',
#                     1270:'h2o2'
#                     }
    
#     y_next = predict_next_from_dict(
#         raw_dict=raw,
#         model_path=r'C:\WPy64-31290\RuiFeng-Metris\Yiting\LSTM\PaperMachine1_LSTM_ProductionRate_Model.h5',
#         scalerX_path=r'C:\WPy64-31290\RuiFeng-Metris\Yiting\LSTM\scaler_X.pkl',
#         scalery_path=r'C:\WPy64-31290\RuiFeng-Metris\Yiting\LSTM\scaler_y.pkl',
#         target_col_name="Brightness",  
#         seq_len=10,
#         tag_name_map=tag_name_map,
#         resample_freq=None，
#         to_tz='Aisa/Shanghai'
#     )

    

    
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
