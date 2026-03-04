import os
import time
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import SSLError, RequestException
import urllib3
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

METRIS_URI = os.getenv('METRIS_URI', "https://f9231aa952b6.ngrok-free.app")
METRIS_USERNAME = os.getenv('METRIS_USERNAME', "Yiting")
METRIS_PASSWORD = os.getenv('METRIS_PASSWORD', "Metris123*")
METRIS_VERIFY = os.getenv('METRIS_VERIFY', "false").lower() in ("1", "true", "yes")
METRIS_URI_LIST = [u.strip() for u in os.getenv('METRIS_URI_LIST', METRIS_URI).split(',') if u.strip()]

RETRY_TOTAL = int(os.getenv('METRIS_RETRY_TOTAL', "2"))
RETRY_BACKOFF = float(os.getenv('METRIS_RETRY_BACKOFF', "0.3"))
RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)
TOKEN_CACHE_TTL = int(os.getenv('METRIS_TOKEN_TTL', "300"))

_session = requests.Session()
_retries = Retry(total=RETRY_TOTAL,
                 backoff_factor=RETRY_BACKOFF,
                 status_forcelist=RETRY_STATUS_FORCELIST,
                 allowed_methods=frozenset(['GET', 'POST']))
_adapter = HTTPAdapter(max_retries=_retries)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

_token_cache = {"token": None, "expires_at": 0, "base_url": None}


class MetrisError(Exception):
    pass

class MetrisAuthError(MetrisError):
    pass

class MetrisConnectionError(MetrisError):
    pass

class MetrisResponseError(MetrisError):
    pass

class MetrisNotFoundError(MetrisError):
    pass


def _normalize_base(base: str) -> str:
    return base.rstrip('/')


def _post_auth_with_session(auth_uri: str, payload: dict):
    return _session.post(auth_uri, json=payload, verify=METRIS_VERIFY, timeout=10)


def get_metris_token():
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now and _token_cache.get("base_url"):
        return {"base_url": _token_cache["base_url"]}, _token_cache["token"], {"Authorization": f"Bearer {_token_cache['token']}"}

    payloads = [
        {"username": METRIS_USERNAME, "password": METRIS_PASSWORD},
        {"userName": METRIS_USERNAME, "password": METRIS_PASSWORD},
        {"UserName": METRIS_USERNAME, "Password": METRIS_PASSWORD},
        {"username": METRIS_USERNAME, "pwd": METRIS_PASSWORD},
    ]

    last_exc = None
    tried = []
    for base in METRIS_URI_LIST:
        base = _normalize_base(base)
        for payload in payloads:
            tried.append({"base": base, "payload": payload})
            auth_uri = f"{base}/api/account/authenticate"
            try:
                resp = _post_auth_with_session(auth_uri, payload)
            except SSLError as e:
                last_exc = e
                if base.startswith("https://"):
                    fallback = "http://" + base.split("://", 1)[1]
                else:
                    fallback = "http://" + base.lstrip("http://").lstrip("https://")
                auth_uri_http = f"{_normalize_base(fallback)}/api/account/authenticate"
                try:
                    resp = _post_auth_with_session(auth_uri_http, payload)
                    base = _normalize_base(fallback)
                except Exception as e2:
                    last_exc = e2
                    continue
            except RequestException as e:
                last_exc = e
                continue

            status = getattr(resp, "status_code", None)
            text = ""
            try:
                text = resp.text
            except Exception:
                pass

            if status == 200:
                try:
                    data = resp.json()
                except Exception:
                    raise MetrisResponseError(f"认证成功但返回非 JSON (base={base}): {text}")
                token = data.get("id") or data.get("token") or data.get("access_token") or (data.get("result") and data["result"].get("id"))
                if not token:
                    raise MetrisResponseError(f"认证成功但未找到 token 字段 (base={base})，返回：{data}")
                _token_cache["token"] = token
                _token_cache["expires_at"] = now + TOKEN_CACHE_TTL
                _token_cache["base_url"] = base
                headers = {"Authorization": f"Bearer {token}"}
                return {"base_url": base}, token, headers

            last_exc = RuntimeError(f"认证失败 (base={base}, status={status}): {text}")

    raise MetrisAuthError(f"METRIS 认证失败，请检查 METRIS_URI、用户名和密码配置。尝试记录: {tried}. 最后错误: {last_exc}")


def get_tags():
    try:
        metris_info, token, headers = get_metris_token()
    except MetrisAuthError as e:
        raise
    except Exception as e:
        raise MetrisAuthError(f"无法认证 METRIS: {e}") from e

    tags_uri = f"{_normalize_base(metris_info['base_url'])}/api/configuration/tags"
    try:
        resp = _session.get(tags_uri, headers=headers, verify=METRIS_VERIFY, timeout=10)
        resp.raise_for_status()
    except SSLError as e:
        raise MetrisConnectionError(f"SSL 错误: {e}") from e
    except RequestException as e:
        raise MetrisConnectionError(f"网络错误获取 tags，请检查网络或 METRIS 服务是否可用: {e}") from e

    try:
        return resp.json()
    except Exception:
        raise MetrisResponseError(f"tags 接口返回非 JSON: {resp.text}")


def get_tag_values(tag_id: int) -> dict:
    try:
        metris_info, token, headers = get_metris_token()
    except MetrisAuthError as e:
        raise

    tag_values_uri = f"{_normalize_base(metris_info['base_url'])}/api/historian/v02/tagvalues"
    params = {"ids": [tag_id]}
    
    print(f"[DEBUG] Requesting tag {tag_id} from {tag_values_uri}")
    print(f"[DEBUG] Headers: {headers}")
    print(f"[DEBUG] Params: {params}")
    
    try:
        resp = _session.get(tag_values_uri, headers=headers, params=params, verify=METRIS_VERIFY, timeout=10)
        print(f"[DEBUG] Response status: {resp.status_code}")
        resp.raise_for_status()
    except SSLError as e:
        print(f"[ERROR] SSL Error: {e}")
        raise MetrisConnectionError(f"SSL 错误 when requesting tagvalues: {e}") from e
    except RequestException as e:
        resp_info = ""
        resp_status = "unknown"
        try:
            resp_status = str(resp.status_code)
            resp_info = f" response: {resp.status_code} {resp.text[:200]}"
        except Exception:
            pass
        print(f"[ERROR] Request error (status {resp_status}): {e}")
        raise MetrisConnectionError(f"请求 tagvalues 接口失败，请检查网络或 METRIS 服务: {e}. {resp_info}") from e

    try:
        result = resp.json()
        print(f"[DEBUG] Response JSON: {result}")
    except Exception as e:
        print(f"[ERROR] Failed to parse response as JSON: {e}")
        print(f"[ERROR] Response text: {resp.text[:200]}")
        raise MetrisResponseError(f"tagvalues 返回非 JSON: {resp.text[:200]}")

    if not isinstance(result, list) or len(result) == 0:
        raise MetrisNotFoundError(
            "查询结果返回空，请检查 METRIS 是否存在对应的 Tag ID，或确认时间范围/权限是否正确。如果这是配置问题，请检查 METRIS_URI、用户名/密码和网络连接。"
        )

    return result[0]


def fix_trend_value(v: dict) -> dict:
    if not isinstance(v, dict):
        return {}
    out = {}
    if 'x' in v:
        try:
            out['x'] = int(v['x'])
        except Exception:
            try:
                dt = datetime.fromisoformat(str(v['x']))
                out['x'] = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
            except Exception:
                out['x'] = v.get('x')
    if 'y' in v:
        try:
            out['y'] = float(v['y'])
        except Exception:
            out['y'] = None
    for k in v:
        if k not in ('x', 'y'):
            out[k] = v[k]
    return out


def fix_trend_values(values: list) -> list:
    values = [fix_trend_value(v) for v in values]
    for d in values:
        if 'x' in d and isinstance(d['x'], (int, float)):
            try:
                d['x'] = datetime.fromtimestamp(d['x'] / 1000, tz=timezone.utc).isoformat()
            except Exception:
                pass
    values = sorted([v for v in values if v.get('x') is not None], key=lambda v: v['x'])
    return values


def get_trend_values(ids, start: datetime = None, end: datetime = None, days: int = 3):
    result = {}
    try:
        metris_info, token, headers = get_metris_token()
    except MetrisAuthError as e:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get token: {e}")
        raise MetrisAuthError(f"Failed to get METRIS token: {e}") from e

    base = metris_info['base_url']
    trend_uri = f'{_normalize_base(base)}/api/historian/v02/trendvalues'
    print(f"[DEBUG] Using METRIS base URL: {base}")
    print(f"[DEBUG] Trend URI: {trend_uri}")

    for tag_id in ids:
        try:
            end_time = end or datetime.now(timezone.utc)
            start_time = start or (end_time - timedelta(days=days))

            trend_params = {
                'tagid': tag_id,
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'timeshift': 0,
                'interpolationmethod': 1,
                'interpolationresolution': 1080,
                'interpolationresolutiontype': 0,
                'aggregatefunction': 0,
                'trackingreferencestep': None
            }

            print(f"[DEBUG] Requesting trend for tag {tag_id} with params: {trend_params}")
            response = _session.get(trend_uri, headers=headers, params=trend_params, verify=METRIS_VERIFY, timeout=30)
            print(f"[DEBUG] Response status for tag {tag_id}: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    raw = response.json()
                    print(f"[DEBUG] Tag {tag_id} trend: got {len(raw) if isinstance(raw, list) else 0} data points")
                    result[tag_id] = raw
                except Exception as e:
                    print(f"[ERROR] Tag {tag_id}: Failed to parse JSON: {e}")
                    result[tag_id] = {'error': f'解析 JSON 失败: {e}'}
            else:
                resp_text = ""
                try:
                    resp_text = response.text[:200]
                except Exception:
                    pass
                error_msg = f"HTTP {response.status_code}"
                if resp_text:
                    error_msg += f": {resp_text}"
                print(f"[ERROR] Tag {tag_id}: {error_msg}")
                result[tag_id] = {'error': error_msg}
        except RequestException as e:
            print(f"[ERROR] Tag {tag_id}: Request exception: {str(e)[:150]}")
            result[tag_id] = {'error': f'请求异常: {str(e)[:100]}'}
        except Exception as e:
            print(f"[ERROR] Tag {tag_id}: {str(e)[:150]}")
            result[tag_id] = {'error': str(e)[:100]}
    
    print(f"[DEBUG] Final trend result keys: {list(result.keys())}")
    return result