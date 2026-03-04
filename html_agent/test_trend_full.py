#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完整测试趋势数据获取流程
1. 直接测试 metris.get_trend_values()
2. 测试 Flask API 端点
"""
import sys
import os
from datetime import datetime, timedelta, timezone
import json

# 测试 1: 直接调用 metris 模块
print("\n" + "="*80)
print("TEST 1: 直接调用 metris.get_trend_values()")
print("="*80)

try:
    from metris import get_trend_values
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=3)
    
    test_tag_ids = [5, 6, 7]
    print(f"请求 Tag IDs: {test_tag_ids}")
    print(f"时间范围: {start_time.isoformat()} 到 {end_time.isoformat()}")
    
    result = get_trend_values(test_tag_ids, start=start_time, end=end_time, days=3)
    
    print(f"\n返回数据结构:")
    print(f"  类型: {type(result)}")
    print(f"  键: {list(result.keys())}")
    
    for tag_id, data in result.items():
        print(f"\n  Tag {tag_id}:")
        print(f"    数据类型: {type(data)}")
        if isinstance(data, list):
            print(f"    数据点数: {len(data)}")
            if len(data) > 0:
                print(f"    第一个数据点: {json.dumps(data[0], indent=6, default=str)}")
                print(f"    最后一个数据点: {json.dumps(data[-1], indent=6, default=str)}")
        elif isinstance(data, dict) and 'error' in data:
            print(f"    错误: {data['error']}")
        else:
            print(f"    数据: {str(data)[:200]}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()


# 测试 2: 调用 Flask API
print("\n" + "="*80)
print("TEST 2: 调用 Flask API /api/metris/trend")
print("="*80)

try:
    import requests
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=3)
    
    params = {
        'tag_ids': '5,6,7',
        'start': start_time.isoformat(),
        'end': end_time.isoformat(),
        'days': 3
    }
    
    print(f"请求参数: {params}")
    
    response = requests.get('http://127.0.0.1:5000/api/metris/trend', params=params, timeout=15)
    print(f"HTTP 状态码: {response.status_code}")
    
    if response.status_code == 200:
        api_result = response.json()
        print(f"\nAPI 返回数据:")
        print(json.dumps(api_result, indent=2, default=str, ensure_ascii=False)[:1000])
        
        if 'trend' in api_result:
            print(f"\ntrend 数据分析:")
            for tag_id, data in api_result['trend'].items():
                if isinstance(data, list):
                    print(f"  Tag {tag_id}: {len(data)} 个数据点")
                else:
                    print(f"  Tag {tag_id}: {type(data)} - {str(data)[:100]}")
    else:
        print(f"错误响应: {response.text[:500]}")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
