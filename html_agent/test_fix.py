#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试修复后的功能
"""
import sys
import os

# 添加当前目录到path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("\n" + "="*70)
print("🔍 测试修复后的功能")
print("="*70)

# 测试1: 认证
print("\n【测试1】METRIS 认证")
print("-" * 70)
try:
    from metris import get_metris_token
    metris_info, token, headers = get_metris_token()
    print(f"✓ 认证成功")
    print(f"  - Base URL: {metris_info.get('base_url')}")
    print(f"  - Token 长度: {len(token) if token else 0}")
    print(f"  - Headers: {headers}")
except Exception as e:
    print(f"✗ 认证失败: {e}")
    sys.exit(1)

# 测试2: 获取单个Tag值
print("\n【测试2】获取 Tag 值 (tag_id=5)")
print("-" * 70)
try:
    from metris import get_tag_values
    result = get_tag_values(5)
    print(f"✓ 获取成功")
    print(f"  - 数据: {result}")
except Exception as e:
    print(f"✗ 获取失败: {e}")

# 测试3: 获取趋势数据
print("\n【测试3】获取趋势数据 (tag_id=5, 3天)")
print("-" * 70)
try:
    from metris import get_trend_values
    from datetime import datetime, timezone, timedelta
    
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=3)
    
    result = get_trend_values([5], start=start_dt, end=end_dt)
    print(f"✓ 获取成功")
    for tag_id, data in result.items():
        if isinstance(data, list):
            print(f"  - Tag {tag_id}: {len(data)} 数据点")
        elif isinstance(data, dict) and 'error' in data:
            print(f"  - Tag {tag_id}: 错误 - {data['error']}")
        else:
            print(f"  - Tag {tag_id}: {data}")
except Exception as e:
    print(f"✗ 获取失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("✓ 测试完成")
print("="*70)
