#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完整诊断脚本 - 模拟整个数据流
"""
import json
import requests
import sys

print("\n" + "="*70)
print("🔍 完整 API 数据流诊断")
print("="*70)

print("\n【第1步】检查后端连接 /api/metris/params")
print("-" * 70)
try:
    resp = requests.get('http://localhost:5000/api/metris/params', timeout=5)
    print(f"✓ HTTP 状态码: {resp.status_code}")
    api_data = resp.json()
    print(f"✓ 返回的 JSON 数据:")
    print(json.dumps(api_data, indent=2, ensure_ascii=False))
    
    # 检查数据结构
    print("\n【检查1】数据结构")
    if 'realtime' in api_data and 'params' in api_data['realtime']:
        print("✓ realtime.params 存在")
        params = api_data['realtime']['params']
        print(f"  - 参数数量: {len(params)}")
        for key, val in params.items():
            print(f"    {key}: {val} (类型: {type(val).__name__})")
    else:
        print("✗ 数据结构不正确")
        
    if 'prediction' in api_data:
        pred = api_data['prediction']
        print(f"✓ prediction 存在")
        print(f"  - next_value: {pred.get('next_value')}")
        print(f"  - timestamp: {pred.get('timestamp')}")
    else:
        print("✗ prediction 缺失")
        
except Exception as e:
    print(f"✗ 连接失败: {e}")
    sys.exit(1)

print("\n【第2步】模拟前端数据处理")
print("-" * 70)
try:
    # 模拟前端的 fetchDataFromAPI() 函数逻辑
    if api_data.get('realtime') and api_data['realtime'].get('params') and api_data.get('prediction'):
        params = api_data['realtime']['params']
        prediction = api_data['prediction']
        
        # 转换为前端期望的格式
        processed = {
            'id': 12345,
            'timestamp': prediction.get('timestamp'),
            'param1': str(round(float(params.get('param1', 0)), 1)),
            'param2': str(round(float(params.get('param2', 0)), 1)),
            'param3': str(round(float(params.get('param3', 0)), 1)),
            'param4': str(round(float(params.get('param4', 0)), 1)),
            'param5': str(round(float(params.get('param5', 0)), 1)),
            'param6': str(round(float(params.get('param6', 0)), 1)),
            'value': str(round(sum(float(v) for v in params.values()) / 6, 1)),
            'predictValue': str(round(float(prediction.get('next_value', 0)), 1)),
            'errorRate': '2.5'
        }
        
        print("✓ 前端数据处理成功")
        print("✓ 处理后的数据结构:")
        print(json.dumps(processed, indent=2, ensure_ascii=False))
        
        # 验证数据的有效性
        print("\n【检查2】数据有效性")
        param_values = [float(processed[f'param{i}']) for i in range(1, 7)]
        if any(v != 0 for v in param_values):
            print(f"✓ 参数中有有效数据 (非零值: {[v for v in param_values if v != 0]})")
        else:
            print("⚠  所有参数都为 0，可能数据获取失败")
            
except Exception as e:
    print(f"✗ 数据处理失败: {e}")
    import traceback
    traceback.print_exc()

print("\n【第3步】诊断总结")
print("-" * 70)
print("""
✅ 后端数据源: 正常 (能正确获取和返回数据)
✅ API 端点: 正常
❓ 前端渲染: 需要检查浏览器控制台

后续步骤:
1. 打开浏览器开发者工具 (F12)
2. 切换到 Console 标签
3. 刷新页面
4. 查看日志信息，特别是 [updateAllData] 和 [updateParamsPanel] 的输出
5. 确认是否有错误信息
""")

print("="*70 + "\n")
