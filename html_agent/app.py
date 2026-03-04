from flask import Flask, render_template, request, Response, stream_with_context
import traceback, requests, os, sys, json, re
from datetime import datetime, timezone
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

app = Flask(__name__, template_folder='templates')
app.config['JSON_AS_ASCII'] = False

from metris import get_tag_values, get_tags, get_trend_values, MetrisNotFoundError, MetrisConnectionError, MetrisAuthError, MetrisResponseError
    
PARAM_TAG_IDS = os.getenv('PARAM_TAG_IDS', '5,6,7,8,9,10')
try:
    PARAM_TAG_IDS = [int(x.strip()) for x in PARAM_TAG_IDS.split(',') if x.strip()]
except Exception:
    PARAM_TAG_IDS = [5, 6, 7, 8, 9, 10]

OLLAMA_LOCAL = os.getenv('OLLAMA_LOCAL', 'http://127.0.0.1:11434/api/generate')


def _normalize_error_text(s: str) -> str:
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return ""
    try:
        out = s
        for _ in range(3):
            if re.search(r'\\u[0-9a-fA-F]{4}', out):
                try:
                    out = out.encode('utf-8').decode('unicode_escape')
                except Exception:
                    break
            else:
                break
        return out
    except Exception:
        return s


def return_json(obj, status=200):

    try:
        text = json.dumps(obj, ensure_ascii=False)
    except Exception:
        try:
            if isinstance(obj, dict):
                cleaned = {k: (_normalize_error_text(v) if isinstance(v, str) else v) for k, v in obj.items()}
                text = json.dumps(cleaned, ensure_ascii=False)
            else:
                text = json.dumps(str(obj), ensure_ascii=False)
        except Exception:
            text = '{"error":"序列化失败"}'
    return Response(text, status=status, mimetype='application/json; charset=utf-8')


def safe_print(msg):
    """Safely print a message to console, avoiding OSError on Windows when output contains
    characters the console cannot handle. Converts to ASCII with backslashreplace as fallback.
    """
    try:
        s = msg if isinstance(msg, str) else repr(msg)
        s_ascii = s.encode('ascii', 'backslashreplace').decode('ascii')
        print(s_ascii)
    except Exception:
        try:
            fallback = (repr(msg) if not isinstance(msg, str) else msg)
            try:
                sys.stderr.write(fallback.encode('ascii', 'backslashreplace').decode('ascii') + '\n')
            except Exception:
                try:
                    sys.stderr.write(repr(fallback)[:200] + '\n')
                except Exception:
                    pass
        except Exception:
            pass


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/model')
def model_page():
    return render_template('chat_v2.html')


@app.route('/diagnostic')
def diagnostic_page():
    return render_template('diagnostic.html')


@app.route('/api/status')
def status():
    return return_json({
        "metris_uri": os.getenv('METRIS_URI'),
        "param_tag_ids": PARAM_TAG_IDS
    })


@app.route('/api/diagnostic', methods=['GET'])
def diagnostic():
    """Diagnostic endpoint to check METRIS connectivity and token."""
    try:
        from metris import get_metris_token
        metris_info, token, headers = get_metris_token()
        return return_json({
            "status": "ok",
            "base_url": metris_info.get('base_url'),
            "token_available": bool(token),
            "token_length": len(token) if token else 0,
            "message": "Successfully authenticated with METRIS"
        })
    except Exception as e:
        safe_print(f"[DIAGNOSTIC] Error: {e}")
        return return_json({
            "status": "error",
            "error": _normalize_error_text(str(e)),
            "message": "Failed to authenticate with METRIS"
        }, status=502)


@app.route('/api/metris/params', methods=['GET'])
def metris_params():
    """
    Return params param1..param6 and a simple prediction.
    Response:
    {
      "realtime": { "params": { "param1": val, ... } },
      "prediction": { "next_value": <num>, "timestamp": "<iso>" }
    }
    """
    try:
        tag_ids = PARAM_TAG_IDS[:6]
        params = {}
        errors = []
        for idx, tag_id in enumerate(tag_ids, start=1):
            try:
                t = get_tag_values(tag_id)
                v = None
                if isinstance(t, dict):
                    v = t.get('value') or t.get('v') or t.get('val') or t.get('Value')
                    try:
                        safe_print(f"[DEBUG] Tag {tag_id}: extracted_value={repr(v)[:120]}")
                    except Exception:
                        pass
                elif isinstance(t, (list, tuple)) and len(t) > 0:
                    first = t[0]
                    if isinstance(first, dict):
                        v = first.get('value') or first.get('v') or first.get('val') or first.get('Value')
                        try:
                            safe_print(f"[DEBUG] Tag {tag_id} (from list): extracted_value={repr(v)[:120]}")
                        except Exception:
                            pass

                val_float = float(v) if v is not None else 0.0
                params[f'param{idx}'] = val_float
                try:
                        safe_print(f"[DEBUG] param{idx}={val_float}")
                except Exception:
                    pass
            except MetrisNotFoundError:
                try:
                    safe_print(f"[WARN] Tag {tag_id} not found")
                except Exception:
                    pass
                params[f'param{idx}'] = 0.0
                errors.append(f"Tag {tag_id}: 未找到")
            except Exception:
                try:
                    safe_print(f"[ERROR] Tag {tag_id} error")
                except Exception:
                    pass
                params[f'param{idx}'] = 0.0
                errors.append(f"Tag {tag_id}: error")

        try:
            safe_print(f"[DEBUG] Final params count: {len(params)}")
        except Exception:
            pass
        realtime_values = list(params.values())
        realtime_value = sum(realtime_values) / max(1, len(realtime_values))
        
        current_timestamp = datetime.now(timezone.utc).isoformat()
        predict_value = realtime_value * (1 + 0.005)

        response = {
            "param1": params.get('param1', 0.0),
            "param2": params.get('param2', 0.0),
            "param3": params.get('param3', 0.0),
            "param4": params.get('param4', 0.0),
            "param5": params.get('param5', 0.0),
            "param6": params.get('param6', 0.0),
            "value": round(realtime_value, 3),
            "predictValue": round(predict_value, 3),
            "timestamp": current_timestamp,
            "errorRate": round((abs(predict_value - realtime_value) / max(abs(realtime_value), 0.001)) * 100, 2),
            "debug": {"errors": errors} if errors else {}
        }
        return return_json(response)
    except Exception as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        msg = "获取 METRIS 参数失败，请检查 METRIS 配置和网络。详情: " + _normalize_error_text(str(e))
        return return_json({"error": msg}, status=500)


@app.route('/api/metris/tag/<int:tag_id>', methods=['GET'])
def metris_tag(tag_id):
    """
    Return the raw tag value info for tag_id.
    Example:
      GET /api/metris/tag/5
    """
    try:
        tag_val = get_tag_values(tag_id)
        return return_json({"tag": tag_val})
    except MetrisNotFoundError as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        emsg = _normalize_error_text(str(e)).strip()
        if emsg and ("查询结果返回空" in emsg or "查询结果为空" in emsg or "不存在对应" in emsg):
            msg = emsg
        else:
            msg = "查询结果为空：请检查 METRIS 是否存在该 Tag ID，或确认时间范围/权限是否正确。更多信息：" + emsg
        return return_json({"error": msg}, status=404)
    except MetrisAuthError as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        emsg = _normalize_error_text(str(e)).strip()
        if emsg and ("认证失败" in emsg or "token" in emsg):
            msg = emsg
        else:
            msg = "认证失败：请检查 METRIS_URI、用户名和密码配置。更多信息：" + emsg
        return return_json({"error": msg}, status=502)
    except MetrisConnectionError as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        emsg = _normalize_error_text(str(e)).strip()
        if emsg and ("连接失败" in emsg or "网络错误" in emsg):
            msg = emsg
        else:
            msg = "连接失败：请检查网络或 METRIS 服务是否可达。更多信息：" + emsg
        return return_json({"error": msg}, status=502)
    except MetrisResponseError as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        emsg = _normalize_error_text(str(e)).strip()
        msg = emsg or "METRIS 返回异常：请检查 METRIS 接口响应格式或权限。"
        return return_json({"error": msg}, status=502)
    except requests.exceptions.SSLError as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        emsg = _normalize_error_text(str(e)).strip()
        msg = "SSL 错误: " + emsg
        return return_json({"error": msg}, status=502)
    except requests.exceptions.RequestException as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        emsg = _normalize_error_text(str(e)).strip()
        msg = "网络请求失败: " + emsg
        return return_json({"error": msg}, status=502)
    except Exception as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        emsg = _normalize_error_text(str(e)).strip()
        msg = "未处理的错误: " + emsg
        return return_json({"error": msg}, status=500)


@app.route('/api/metris/trend', methods=['GET'])
def metris_trend():
    """Return trend values for a given tag and time range.
    Query params: tag_id (int), start (ISO datetime), end (ISO datetime), days (int)
    """
    try:
        tag_ids_raw = request.args.get('tag_ids') or request.args.get('tag_id') or request.args.get('id')
        if not tag_ids_raw:
            safe_print("[WARN] No tag_ids provided")
            return return_json({"error": "missing tag_id or tag_ids"}, status=400)
        tag_ids = []
        try:
            if isinstance(tag_ids_raw, str) and ',' in tag_ids_raw:
                for part in tag_ids_raw.split(','):
                    part = part.strip()
                    if not part:
                        continue
                    tag_ids.append(int(part))
            else:
                tag_ids = [int(tag_ids_raw)]
        except Exception as e:
            safe_print(f"[ERROR] Invalid tag_id(s): {e}")
            return return_json({"error": "invalid tag_id(s)"}, status=400)

        safe_print(f"[DEBUG] Fetching trend for tags: {tag_ids}")
        
        start_s = request.args.get('start')
        end_s = request.args.get('end')
        days = int(request.args.get('days') or 3)

        start_dt = None
        end_dt = None
        try:
            if end_s:
                s = end_s.replace('Z', '+00:00')
                end_dt = datetime.fromisoformat(s)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
            if start_s:
                s = start_s.replace('Z', '+00:00')
                start_dt = datetime.fromisoformat(s)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            safe_print(f"[ERROR] Invalid datetime format: {e}")
            return return_json({"error": "invalid start/end datetime format; use ISO format"}, status=400)

        safe_print(f"[DEBUG] Time range: {start_dt} to {end_dt}")
        
        data = get_trend_values(tag_ids, start=start_dt, end=end_dt, days=days)
        safe_print(f"[DEBUG] Data returned from get_trend_values: type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        
        counts = {tid: (len(v) if isinstance(v, list) else 0) for tid, v in data.items()}
        safe_print(f"[DEBUG] Data counts: {counts}")
        
        return return_json({"tags": tag_ids, "trend": data, "counts": counts})
    except MetrisAuthError as e:
        safe_print(f"[ERROR] Auth error: {e}")
        return return_json({"error": _normalize_error_text(str(e))}, status=502)
    except Exception as e:
        safe_print(f"[ERROR] Unhandled exception: {e}")
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        return return_json({"error": _normalize_error_text(str(e))}, status=500)


@app.route('/api/metris/analyze', methods=['POST'])
def metris_analyze():
    """Fetch trend data for the requested tag (or accept provided data) and send to local model for analysis.
    POST JSON: { tag_id: int, start: iso?, end: iso?, days: int?, data: optional array, model: optional }
    """
    try:
        payload = request.get_json(silent=True) or {}
        tag_id = payload.get('tag_id')
        start_s = payload.get('start')
        end_s = payload.get('end')
        days = int(payload.get('days') or 3)

        data_for_analysis = None
        if payload.get('data'):
            data_for_analysis = payload.get('data')
        elif tag_id:
            start_dt = None
            end_dt = None
            try:
                if end_s:
                    end_dt = datetime.fromisoformat(end_s)
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                if start_s:
                    start_dt = datetime.fromisoformat(start_s)
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
            except Exception:
                return return_json({"error": "invalid start/end datetime format; use ISO format"}, status=400)
            trend = get_trend_values([int(tag_id)], start=start_dt, end=end_dt, days=days)
            data_for_analysis = trend.get(int(tag_id))

        if not data_for_analysis:
            sample_info = None
            try:
                if isinstance(data_for_analysis, list):
                    sample_info = {"count": len(data_for_analysis), "sample": data_for_analysis[:3]}
                else:
                    sample_info = {"type": str(type(data_for_analysis)), "repr": str(data_for_analysis)[:200]}
            except Exception:
                sample_info = None
            return return_json({"error": "no data for analysis", "info": sample_info}, status=400)

        sample = data_for_analysis
        try:
            series = []
            if isinstance(sample, list):
                for p in sample[:200]:
                    t = p.get('x') or p.get('time') or p.get('timestamp')
                    y = p.get('y') or p.get('value') or p.get('v')
                    series.append({"time": t, "value": y})
        except Exception:
            series = sample

        prompt = (
            "请作为数据分析师，简明分析以下时间序列数据。先给出关键统计指标（最小、最大、均值、标准差），"
            "指出可能的异常点（简要说明原因或怀疑的原因），并给出 3 条可操作的建议。\n\n"
            f"数据（前200条或全部）: {json.dumps(series, ensure_ascii=False)}\n\n"
            "请以清晰的段落输出，先给统计数值表格，然后结论与建议。"
        )

        model_name = payload.get('model') or os.getenv('OLLAMA_MODEL', 'gemma3:4b')

        try:
            import threading, time as _time
            out_dir = os.path.join(os.path.dirname(__file__), 'analysis_results')
            os.makedirs(out_dir, exist_ok=True)

            job_ts = int(_time.time())

            def _run_and_save(series_data, tag, model_name, job_ts_inner):
                fname = f"analysis_{tag}_{job_ts_inner}.json"
                path = os.path.join(out_dir, fname)
                result_obj = {"tag": tag, "started_at": _time.strftime('%Y-%m-%dT%H:%M:%SZ', _time.gmtime(job_ts_inner))}
                try:
                    resp = requests.post(OLLAMA_LOCAL, json={"model": model_name, "prompt": prompt, "max_tokens": 1024, "temperature": 0.2, "stream": False}, timeout=120)
                    try:
                        model_txt = resp.json()
                    except Exception:
                        model_txt = resp.text
                    result_obj["result"] = model_txt
                except Exception as e:
                    result_obj["error"] = str(e)
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump({"meta": result_obj, "input_sample": series_data}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            t = threading.Thread(target=_run_and_save, args=(series, tag_id or 'unknown', model_name, job_ts), daemon=True)
            t.start()
            job_id = f"analysis_{tag_id}_{job_ts}" if tag_id else f"analysis_{job_ts}"
            return return_json({"status": "submitted", "job_id": job_id})
        except Exception as e:
            return return_json({"error": f"failed to submit analysis: {e}"}, status=500)

    except Exception as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        return return_json({"error": _normalize_error_text(str(e))}, status=500)


@app.route('/api/ollama/generate', methods=['POST'])
def proxy_ollama_generate():
    """
    Proxy POST to local Ollama /api/generate, preserving streaming.
    """
    try:
        body = request.get_data()
        headers = {}
        for k, v in request.headers.items():
            if k.lower() in ('host', 'content-length', 'transfer-encoding', 'accept-encoding'):
                continue
            headers[k] = v
        headers['Content-Type'] = 'application/json'

        resp = requests.post(OLLAMA_LOCAL, headers=headers, data=body, stream=True, timeout=60)

        def generate():
            try:
                for chunk in resp.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk
            except Exception as e:
                yield str.encode(f'\n{{"error":"proxy stream error: {_normalize_error_text(str(e))}"}}\n')
            finally:
                try:
                    resp.close()
                except:
                    pass

        return Response(stream_with_context(generate()), status=resp.status_code,
                        content_type=resp.headers.get('Content-Type', 'application/octet-stream'))
    except requests.exceptions.RequestException as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        msg = f"请求 Ollama 失败: {_normalize_error_text(str(e))}"
        return return_json({"error": msg}, status=502)
    except Exception as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        msg = _normalize_error_text(str(e))
        return return_json({"error": msg}, status=500)


@app.route('/api/metris/analysis/<job_id>', methods=['GET'])
def metris_analysis_status(job_id):
    """Check analysis_results for a given job_id. Returns pending/done/error and file content when done."""
    try:
        if not re.match(r'^[A-Za-z0-9_\-:]+$', job_id):
            return return_json({"error": "invalid job_id"}, status=400)
        out_dir = os.path.join(os.path.dirname(__file__), 'analysis_results')
        if not os.path.isdir(out_dir):
            return return_json({"status": "pending"})
        found = None
        for fn in os.listdir(out_dir):
            if fn == f"{job_id}.json" or fn.startswith(job_id + '_') or fn.startswith(job_id):
                found = os.path.join(out_dir, fn)
                break
        if not found:
            return return_json({"status": "pending"})
        try:
            with open(found, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            return return_json({"status": "error", "error": _normalize_error_text(str(e))}, status=500)
        meta = data.get('meta') if isinstance(data, dict) else None
        if meta and meta.get('error'):
            return return_json({"status": "error", "error": meta.get('error')})
        return return_json({"status": "done", "file": data})
    except Exception as e:
        try:
            traceback.print_exc()
        except Exception:
            try:
                safe_print("Traceback suppressed (console encoding issue)")
            except Exception:
                pass
        return return_json({"error": _normalize_error_text(str(e))}, status=500)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)