#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 /api/metris/trend 端点
"""
import json
import requests
from datetime import datetime, timedelta, timezone

print("\n" + "="*70)
print("测试 /api/metris/trend 端点")
print("="*70)

# 测试参数
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=1)

params = {
    'tag_ids': '4,8',
    'start': start_time.isoformat(),
    'end': end_time.isoformat(),
    'days': 1
}

print(f"\n请求参数:")
print(f"  tag_ids: {params['tag_ids']}")
print(f"  start: {params['start']}")
print(f"  end: {params['end']}")

try:
    response = requests.get('http://127.0.0.1:5000/api/metris/trend', params=params, timeout=15)
    print(f"\n状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n返回的 JSON 数据:")
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        
        # 检查数据结构
        print(f"\n📊 数据分析:")
        if 'trend' in data:
            trend_data = data['trend']
            print(f"  trend 类型: {type(trend_data)}")
            if isinstance(trend_data, list):
                print(f"  trend 是列表，长度: {len(trend_data)}")
                if len(trend_data) > 0:
                    print(f"  第一个元素: {json.dumps(trend_data[0], indent=4, default=str)[:300]}...")
            elif isinstance(trend_data, dict):
                print(f"  trend 是字典，键: {list(trend_data.keys())}")
                for tag_id, values in trend_data.items():
                    if isinstance(values, list):
                        print(f"    Tag {tag_id}: {len(values)} 条数据")
                    elif isinstance(values, dict) and 'error' in values:
                        print(f"    Tag {tag_id}: {values['error']}")
    else:
        print(f"返回的文本: {response.text}")
except Exception as e:
    print(f"✗ 连接失败: {e}")
    print("确保 Flask 服务器正在运行: python app.py")

print("\n" + "="*70)
