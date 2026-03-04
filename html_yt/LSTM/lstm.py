import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.preprocessing import StandardScaler,RobustScaler,MinMaxScaler
from sklearn.metrics import mean_squared_error, r2_score,mean_absolute_error
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping,ReduceLROnPlateau
import tensorflow as tf
import joblib
from flask import Flask
from flask import Flask, render_template
import numpy as np
import requests
import os
import dateutil.parser
import pytz
from datetime import datetime, timedelta, timezone
from typing import Optional,Dict,List,Tuple
from dotenv import load_dotenv

load_dotenv()

METRIS_URI = os.getenv('METRIS_URI')
METRIS_USERNAME = os.getenv('METRIS_USERNAME')
METRIS_PASSWORD = os.getenv('METRIS_PASSWORD')

def get_metris_token():
    auth_data = {"username": METRIS_USERNAME, "password": METRIS_PASSWORD}
    auth_uri = f"{METRIS_URI}/api/account/authenticate"
    response = requests.post(auth_uri, json=auth_data, verify=False)  
    token_data = response.json()  
    token = token_data.get("id") 
    headers = {"Authorization": f"Bearer {token}"}  
    return {"base_url": METRIS_URI}, token, headers

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

                result[tag_id] = raw_data
            except Exception as e:
                print("解析 JSON 失败：", e)
                result[tag_id] = {'error': 'Invalid JSON'}
        else:
            result[tag_id] = {'error': f"Failed to retrieve data for tag_id {tag_id}"}

    return result

def parse_mixed_iso8601(series: pd.Series, to_tz: str | None = "Asia/Shanghai") -> pd.Series:

    s = series.astype(str).str.strip()
    s = s.str.replace(' ', 'T', regex=False) 
   
    try:
        dt = pd.to_datetime(s, format='ISO8601', errors='coerce', utc=True)
    except TypeError:
        dt = pd.to_datetime(s, errors='coerce', utc=True)

    mask = dt.isna()
    if mask.any():
        dt2 = pd.to_datetime(s[mask], errors='coerce', utc=True, infer_datetime_format=True)
        dt[mask] = dt2
    if to_tz:
              
        if getattr(dt.dt, "tz", None) is None:
            dt = dt.dt.tz_localize("UTC")
        dt = dt.dt.tz_convert(to_tz)

    return dt


def dict_to_timeseries_df(
    raw_dict: Dict,
    tag_name_map: Optional[Dict] = None,
    resample_freq: Optional[str] = None,
    to_tz: Optional[str] = "Asia/Shanghai",
    sort_and_fill: bool = True
) -> pd.DataFrame:
    series_list, col_names = [], []

    for key, lst in raw_dict.items():
        if not lst:
            continue

        df = pd.DataFrame(lst)
        if 'x' not in df or 'y' not in df:
            cols_lower = {c.lower(): c for c in df.columns}
            df.rename(columns={cols_lower.get('x', 'x'): 'x', cols_lower.get('y', 'y'): 'y'}, inplace=True)

        df['x'] = parse_mixed_iso8601(df['x'], to_tz=to_tz)

        df = df.dropna(subset=['x'])
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

    if sort_and_fill:
        combined = combined.sort_index()
        combined = combined.ffill().bfill() 

    if resample_freq:
        combined = (combined
                    .resample(resample_freq)
                    .mean()
                    .interpolate('time')
                    .ffill()
                    .bfill())

    return combined


def latest_aligned_block(
    raw_dict: Dict,
    seq_len: int = 10,
    tag_name_map: Optional[Dict] = None,
    resample_freq: Optional[str] = None,
    to_tz: Optional[str] = "Asia/Shanghai",
    pad_if_short: bool = False
) -> pd.DataFrame:
    df = dict_to_timeseries_df(
        raw_dict=raw_dict,
        tag_name_map=tag_name_map,
        resample_freq=resample_freq,
        to_tz=to_tz
    )

    if len(df) >= seq_len:
        return df.iloc[-seq_len:]
    else:
        if not pad_if_short:
            raise ValueError(f"数据点仅 {len(df)} 条，不足 {seq_len}。可将 pad_if_short=True 或降低 seq_len。")

        first_row = df.iloc[0:1]
        pad_needed = seq_len - len(df)
        if resample_freq:
            start_time = df.index[0]
            pad_idx = pd.date_range(end=start_time, periods=pad_needed+1, freq=resample_freq)[:-1]
        else:
            start_time = df.index[0]
            pad_idx = pd.date_range(end=start_time, periods=pad_needed+1, freq='1S')[:-1]
        pad_df = pd.concat([first_row] * pad_needed, axis=0)
        pad_df.index = pad_idx
        filled = pd.concat([pad_df, df], axis=0).sort_index()
        return filled.iloc[-seq_len:]


def train_lstm_from_df(
    df: pd.DataFrame,
    target_col: str,
    seq_len: int = 30,
    epochs: int = 5,
    batch_size: int = 32,
    scaler_type: str = "standard",  
    model_path: str = 'PaperMachine1_LSTM_ProductionRate_Model.keras',
    scalerX_path: str = 'scaler_X.pkl',
    scalery_path: str = 'scaler_y.pkl',
    topN_features: Optional[int] = None,  
    verbose: int = 1
) -> Dict:

    if target_col not in df.columns:
        raise ValueError(f"目标列 {target_col} 不在 df.columns: {list(df.columns)}")

    feature_cols = [c for c in df.columns if c != target_col]
    if len(feature_cols) == 0:
        raise ValueError("没有可用特征列（除了目标列之外至少需要1列）。")

    if topN_features is not None and topN_features < len(feature_cols):
        corrs = df.corr(numeric_only=True)[target_col].drop(labels=[target_col], errors='ignore')
        top_cols = corrs.abs().sort_values(ascending=False).index.tolist()[:topN_features]
        feature_cols = top_cols

    X_all = df[feature_cols].values
    y_all = df[target_col].values.reshape(-1, 1)

    allowed_scalers = {"standard": StandardScaler, "robust": RobustScaler, "minmax": MinMaxScaler}
    scaler_type_X = scaler_type
    scaler_type_y = scaler_type
    scaler_X = allowed_scalers[scaler_type_X]()
    scaler_y = allowed_scalers[scaler_type_y]()
    X_scaled = scaler_X.fit_transform(X_all)
    y_scaled = scaler_y.fit_transform(y_all)

    def create_sequences(features, target, win):
        X, y = [], []
        for i in range(len(features) - win):
            X.append(features[i:i+win])
            y.append(target[i+win])
        return np.array(X), np.array(y)

    if len(df) <= seq_len + 1:
        new_seq_len = max(2, len(df) - 2)
        print(f"[警告] 数据点仅 {len(df)} 条，不足以使用 seq_len={seq_len}。自动将 seq_len 调整为 {new_seq_len}。")
        seq_len = new_seq_len

    X, y = create_sequences(X_scaled, y_scaled, seq_len)

    if len(X) < 10:
        print(f"[提示] 当前样本量仅 {len(X)}，泛化能力可能较差。建议增加采样频率与数据时长。")

    split_idx = int(len(X) * 0.7) if len(X) > 1 else 1
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    model = Sequential([
        LSTM(32, return_sequences=False, input_shape=(seq_len, X.shape[2]),
             kernel_regularizer=tf.keras.regularizers.l2(1e-4)),
        Dropout(0.3),
        Dense(1)
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss='mse')

    es    = EarlyStopping(monitor='val_loss', patience=8, restore_best_weights=True)
    rlrop = ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=4, min_lr=1e-5)

    val_split = 0.2 if len(X_train) >= 50 else 0.0
    callbacks = [es, rlrop] if val_split > 0 else [es]

    history = model.fit(
        X_train, y_train,
        validation_split=val_split,
        epochs=epochs,
        batch_size=max(8, min(batch_size, len(X_train))) if len(X_train) else 1,
        verbose=verbose,
        callbacks=callbacks
    )

    y_train_pred = model.predict(X_train, verbose=0) if len(X_train) else np.array([])
    y_test_pred  = model.predict(X_test,  verbose=0) if len(X_test)  else np.array([])

    def safe_metrics(y_true, y_pred):
        if len(y_true) == 0 or len(y_pred) == 0:
            return np.nan, np.nan
        return mean_squared_error(y_true, y_pred), r2_score(y_true, y_pred)

    train_mse, train_r2 = safe_metrics(y_train, y_train_pred)
    test_mse,  test_r2  = safe_metrics(y_test, y_test_pred)

    print(f"RESULT: Train MSE = {train_mse:.6f} | R² = {train_r2:.4f}")
    print(f"RESULT: Test  MSE = {test_mse:.6f} | R² = {test_r2:.4f}")

    def eval_real_unit(y_true_s, y_pred_s, name="Test"):
        if len(y_true_s) == 0 or len(y_pred_s) == 0:
            print(f"[{name} Real] 无样本")
            return
        y_true = scaler_y.inverse_transform(y_true_s).ravel()
        y_pred = scaler_y.inverse_transform(y_pred_s).ravel()
        mse = mean_squared_error(y_true, y_pred); mae = mean_absolute_error(y_true, y_pred); r2 = r2_score(y_true, y_pred)
        print(f"[{name} Real] MSE={mse:.4f}, MAE={mae:.4f}, R²={r2:.4f}")
    eval_real_unit(y_train, y_train_pred, "Train")
    eval_real_unit(y_test,  y_test_pred,  "Test")

    if len(y_test) > 2:
        y_test_real = scaler_y.inverse_transform(y_test).ravel()
 
        naive = y_test_real[:-1]
        print(f"[Baseline] Naive  MSE={mean_squared_error(y_test_real[1:], naive):.4f} "
              f"R²={r2_score(y_test_real[1:], naive):.4f}")
  
        if len(y_test_real) >= seq_len:
            ma = np.convolve(y_test_real, np.ones(seq_len)/seq_len, mode='valid')
            print(f"[Baseline] SMA({seq_len}) MSE={mean_squared_error(y_test_real[seq_len-1:], ma):.4f} "
                  f"R²={r2_score(y_test_real[seq_len-1:], ma):.4f}")

    model.save(model_path)  
    joblib.dump(scaler_X, scalerX_path)
    joblib.dump(scaler_y, scalery_path)
    print(f"RESULT: 模型与 Scaler 已保存：\n - {model_path}\n - {scalerX_path}\n - {scalery_path}")

    return {
        "model_path": model_path,
        "scalerX_path": scalerX_path,
        "scalerY_path": scalery_path,
        "seq_len": seq_len,
        "feature_cols": feature_cols,
        "target_col": target_col,
        "history": history.history
    }


if __name__ == '__main__':
    tag_ids = [787,11483,12071,749,748,11487,1270]
    result = get_trend_values(tag_ids)
    print(result)
    tag_name_map = {787:"Brightness",
                    11483:'Power',
                    12071:'Consis_HCR1_SS',
                    749:'Temperature',
                    748:'lever',
                    11487:'tower',
                    1270:'h2o2'
                    }
    
    df = dict_to_timeseries_df(result, tag_name_map=tag_name_map, resample_freq=None,to_tz = 'Asia/Shanghai')
    print(df)
    info = train_lstm_from_df(
            df=df,
            target_col= "Brightness",
            seq_len = 10,
            epochs = 50,
            batch_size = 32,
            scaler_type='standard',
            model_path = r'C:\WPy64-31290\RuiFeng-Metris\Yiting\LSTM\PaperMachine1_LSTM_ProductionRate_Model.h5',
            scalerX_path = r'C:\WPy64-31290\RuiFeng-Metris\Yiting\LSTM\scaler_X.pkl',
            scalery_path = r'C:\WPy64-31290\RuiFeng-Metris\Yiting\LSTM\scaler_y.pkl',
            topN_features=None,
            verbose=1
        )
    
