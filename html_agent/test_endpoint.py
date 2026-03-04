#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断脚本：测试完整的趋势数据流
"""
import json
import requests
from datetime import datetime, timedelta, timezone

print("\n" + "="*70)
print("【完整诊断】后端 + 前端数据流测试")
print("="*70)

# 1. 测试后端是否在运行
print("\n[1] 检查 Flask 服务器...")
try:
    resp = requests.get('http://127.0.0.1:5000/', timeout=2)
    print("✓ Flask 服务器运行中")
except Exception as e:
    print(f"✗ Flask 服务器未运行: {e}")
    exit(1)

# 2. 测试参数端点
print("\n[2] 测试 /api/metris/params...")
try:
    resp = requests.get('http://127.0.0.1:5000/api/metris/params', timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        params = data.get('realtime', {}).get('params', {})
        print(f"✓ 返回参数数据: {list(params.keys())}")
        param_values = [v for k, v in params.items() if v != 0]
        if param_values:
            print(f"  有效参数值: {len(param_values)}/{len(params)}")
        else:
            print(f"  ⚠ 所有参数都是 0")
    else:
        print(f"✗ 状态码 {resp.status_code}")
except Exception as e:
    print(f"✗ 错误: {e}")

# 3. 测试趋势数据端点
print("\n[3] 测试 /api/metris/trend (单个 Tag)...")
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=1)

try:
    params = {
        'tag_id': '4',
        'start': start_time.isoformat(),
        'end': end_time.isoformat()
    }
    resp = requests.get('http://127.0.0.1:5000/api/metris/trend', params=params, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ 返回数据结构: tags={data.get('tags')}")
        
        trend_data = data.get('trend', {})
        print(f"  trend 类型: {type(trend_data).__name__}")
        
        if isinstance(trend_data, dict):
            for tag_id, values in trend_data.items():
                if isinstance(values, list):
                    print(f"  ✓ Tag {tag_id}: {len(values)} 数据点")
                elif isinstance(values, dict) and 'error' in values:
                    print(f"  ✗ Tag {tag_id}: {values['error']}")
        
        counts = data.get('counts', {})
        print(f"  数据计数: {counts}")
    else:
        print(f"✗ 状态码 {resp.status_code}: {resp.text[:100]}")
except Exception as e:
    print(f"✗ 错误: {e}")

# 4. 测试多标签趋势
print("\n[4] 测试 /api/metris/trend (多个 Tags)...")
try:
    params = {
        'tag_ids': '4,5,8',
        'start': start_time.isoformat(),
        'end': end_time.isoformat()
    }
    resp = requests.get('http://127.0.0.1:5000/api/metris/trend', params=params, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        trend_data = data.get('trend', {})
        counts = data.get('counts', {})
        
        total_points = sum(counts.values())
        print(f"✓ 返回 {len(trend_data)} 个标签的数据")
        print(f"  总数据点数: {total_points}")
        
        for tag_id, count in counts.items():
            print(f"    Tag {tag_id}: {count} 数据点")
    else:
        print(f"✗ 状态码 {resp.status_code}")
except Exception as e:
    print(f"✗ 错误: {e}")

print("\n" + "="*70)
print("诊断完成！检查上面的输出确认数据流是否正常")
print("="*70 + "\n")
