#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：直接调用后端 API 并查看返回数据
"""

import requests
import json
from metris import get_tag_values, get_tags, METRIS_URI, PARAM_TAG_IDS

print("="*60)
print("测试 METRIS 连接")
print("="*60)

print(f"\n[1] 配置信息:")
print(f"  METRIS_URI: {METRIS_URI}")
print(f"  PARAM_TAG_IDS: {PARAM_TAG_IDS}")

print(f"\n[2] 直接测试 get_tag_values():")
for tag_id in PARAM_TAG_IDS[:3]:
    print(f"\n  --- 测试 Tag {tag_id} ---")
    try:
        result = get_tag_values(tag_id)
        print(f"    类型: {type(result)}")
        print(f"    结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"    ❌ 错误: {e}")

print(f"\n[3] 调用 /api/metris/params 端点:")
try:
    resp = requests.get('http://localhost:5000/api/metris/params')
    print(f"  状态码: {resp.status_code}")
    data = resp.json()
    print(f"  返回数据:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"  ❌ 错误: {e}")

print("\n" + "="*60)
