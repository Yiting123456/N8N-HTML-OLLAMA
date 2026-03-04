
import os
import io
import time
import uuid
import json
import traceback
from threading import Lock
from flask import Flask, render_template, request, Response, jsonify, stream_with_context
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__, template_folder='templates')

OLLAMA_LOCAL = os.getenv('OLLAMA_LOCAL', 'http://127.0.0.1:11434/api/generate')
METRIS_URI = os.getenv('METRIS_URI')
METRIS_USERNAME = os.getenv('METRIS_USERNAME')
METRIS_PASSWORD = os.getenv('METRIS_PASSWORD')

CONFIG_PATH = 'config.json'
RAG_STORE_DIR = 'rag_store'   
UPLOADS_DIR = 'uploads'      

AGENT_CONFIG = {
    "sentence_model": os.getenv('SENTENCE_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2'),
    "threshold": float(os.getenv('SEM_THRESHOLD', '0.45')),
    "top_k": int(os.getenv('SEM_TOPK', '3'))
}

desc_dict = {
    30: '废料磨浆机 A 流量',
    31: '废料磨浆机 B 出口流量',
    46: '废料磨浆机 A 出口压力',
    47: '废料磨浆机 B 出口压力',
    57: '废料磨浆机 A 出口温度',
    58: '废料磨浆机 B 出口温度',
    66: '废料磨浆机功率监控',
    1490: '未精制废料槽液位',
    1492: '精磨后进料浓度',
    1493: '废料磨浆机比能量',
    375: '1# 氢氧化钠储槽液位',
    392: '1# 过氧化氢储槽液位',
    1257: '浸渍 1 氢氧化钠浓度',
    1271: '浸渍 2 过氧化氢浓度',
    1288: '磨浆机 1 过氧化氢浓度',
    1302: '新鲜水总流量',
    1350: '过氧化氢总添加流量',
    1351: '氢氧化钠总添加流量',
    11654: '实际产量',
    11655: '修正产量',
    11971: '化验室白度数据',
    11972: '化验室游离度数据',
    11973: '化验室抗张指数数据',
    11610: '磨浆机 1 运行状态'
}

RAG_INDICES = {}  
RAG_LOCK = Lock()

try:
    from langchain_community.vectorstores import DocArrayInMemorySearch
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_ollama import OllamaEmbeddings
    import PyPDF2
except Exception as e:
    RAG_AVAILABLE = False
    print("RAG not available (missing dependencies):", e)
    traceback.print_exc()

def load_agent_config():
    global AGENT_CONFIG
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                j = json.load(f)
                AGENT_CONFIG.update(j)
                print("Loaded AGENT_CONFIG from", CONFIG_PATH)
        except Exception:
            print("Failed to load config.json, continuing with defaults")
            traceback.print_exc()

def save_agent_config():
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(AGENT_CONFIG, f, ensure_ascii=False, indent=2)
        print("Saved AGENT_CONFIG to", CONFIG_PATH)
        return True
    except Exception as e:
        print("Failed to save config.json:", e)
        traceback.print_exc()
        return False

def ensure_rag_store():
    os.makedirs(RAG_STORE_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)

def save_rag_index_to_disk(index_id):
    """
    Persist index metadata and docs (text chunks) to rag_store/{index_id}.json.
    Note: vectorstore is not serialized; it will be rebuilt on startup when loading.
    """
    entry = RAG_INDICES.get(index_id)
    if not entry:
        raise KeyError("index_id not found")
    meta = {
        "id": entry["id"],
        "name": entry["name"],
        "created_at": entry["created_at"],
        "file_paths": entry.get("file_paths", []),
        "docs": entry.get("docs", []),
        "embedding_model": entry.get("embedding_model", AGENT_CONFIG.get("sentence_model"))
    }
    path = os.path.join(RAG_STORE_DIR, f"{index_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return path

def load_rag_indices_from_disk():
    """
    Load all rag_store/*.json, reconstruct RAG_INDICES and rebuild vectorstores in memory.
    """
    if not RAG_AVAILABLE:
        print("RAG not available; skipping load from disk.")
        return
    ensure_rag_store()
    files = [f for f in os.listdir(RAG_STORE_DIR) if f.endswith('.json')]
    for fn in files:
        try:
            path = os.path.join(RAG_STORE_DIR, fn)
            with open(path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            index_id = meta['id']
            emb_model = meta.get('embedding_model', AGENT_CONFIG.get('sentence_model'))
            embeddings = OllamaEmbeddings(model=emb_model, base_url=None)
            vect = DocArrayInMemorySearch.from_texts(meta.get('docs', []), embeddings)
            RAG_INDICES[index_id] = {
                "id": index_id,
                "name": meta.get("name"),
                "created_at": meta.get("created_at"),
                "file_paths": meta.get("file_paths", []),
                "docs": meta.get("docs", []),
                "vectorstore": vect,
                "embedding_model": emb_model
            }
            print("Loaded RAG index:", index_id, meta.get("name"))
        except Exception as e:
            print("Failed to load rag index file", fn, e)
            traceback.print_exc()

def save_upload_file(file_storage):
    ensure_rag_store()
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    filename = file_storage.filename
    uid = f"{int(time.time()*1000)}_{filename}"
    path = os.path.join(UPLOADS_DIR, uid)
    file_storage.save(path)
    return path

def extract_text_from_pdf(path):
    try:
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            pages = []
            for p in reader.pages:
                try:
                    pages.append(p.extract_text() or "")
                except Exception:
                    pages.append("")
            return "\n".join(pages)
    except Exception as e:
        raise RuntimeError(f"PDF parse failed: {e}")

def extract_text_from_txt(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f"Text read failed: {e}")

# ---------------- RAG build/search ----------------
def build_rag_index(name, file_paths, chunk_size=1000, chunk_overlap=150, embedding_model=None):
    if not RAG_AVAILABLE:
        raise RuntimeError("RAG not available (missing dependencies).")
    # extract text from files
    texts = []
    for p in file_paths:
        lower = p.lower()
        if lower.endswith('.pdf'):
            texts.append(extract_text_from_pdf(p))
        else:
            texts.append(extract_text_from_txt(p))
    combined_text = "\n\n".join(texts)
    if not combined_text.strip():
        raise RuntimeError("No text extracted from files.")
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    # split_text returns list of strings for this splitter
    docs = splitter.split_text(combined_text) if hasattr(splitter, 'split_text') else [combined_text]
    emb_model = embedding_model or AGENT_CONFIG.get('sentence_model', 'nomic-embed-text')
    embeddings = OllamaEmbeddings(model=emb_model, base_url=None)
    vect = DocArrayInMemorySearch.from_texts(docs, embeddings)
    index_id = str(uuid.uuid4())
    RAG_INDICES[index_id] = {
        "id": index_id,
        "name": name,
        "created_at": time.time(),
        "file_paths": file_paths,
        "docs": docs,
        "vectorstore": vect,
        "embedding_model": emb_model
    }
    # persist to disk
    save_rag_index_to_disk(index_id)
    return index_id

def rag_search(index_id, query, k=3):
    entry = RAG_INDICES.get(index_id)
    if not entry:
        raise KeyError("index_id not found")
    vect = entry['vectorstore']
    results = vect.search(query, k=k)
    matches = []
    for r in results:
        try:
            page_content = getattr(r, 'page_content', str(r))
            metadata = getattr(r, 'metadata', {}) or {}
        except Exception:
            page_content = str(r)
            metadata = {}
        matches.append({"text": page_content, "metadata": metadata})
    return matches

# ---------------- On startup: load config and existing RAG indices ----------------
load_agent_config()
ensure_rag_store()
if RAG_AVAILABLE:
    # load and rebuild indices (may be time-consuming)
    try:
        load_rag_indices_from_disk()
    except Exception:
        traceback.print_exc()

# ---------------- Flask routes ----------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/model')
def model_page():
    return render_template('chat.html')

@app.route('/api/status')
def status():
    return {
        "ollama_proxy": OLLAMA_LOCAL,
        "metris_configured": bool(METRIS_URI and METRIS_USERNAME and METRIS_PASSWORD),
        "rag_available": RAG_AVAILABLE,
        "rag_indices": [{"id": v["id"], "name": v["name"], "created_at": v["created_at"]} for v in RAG_INDICES.values()]
    }

# ---------------- Ollama proxy (streaming) ----------------
@app.route('/api/ollama/generate', methods=['POST'])
def proxy_ollama_generate():
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
                yield str.encode(f'\n{{"error":"proxy stream error: {e}"}}\n')
            finally:
                try: resp.close()
                except: pass
        return Response(stream_with_context(generate()), status=resp.status_code, content_type=resp.headers.get('Content-Type','application/octet-stream'))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------- Agent realtime (lightweight substring matching) ----------------
def get_metris_token():
    if not METRIS_URI or not METRIS_USERNAME or not METRIS_PASSWORD:
        raise RuntimeError("METRIS not configured in .env")
    auth_data = {"username": METRIS_USERNAME, "password": METRIS_PASSWORD}
    auth_uri = f"{METRIS_URI}/api/account/authenticate"
    r = requests.post(auth_uri, json=auth_data, verify=False, timeout=10)
    r.raise_for_status()
    token_data = r.json()
    token = token_data.get("id")
    headers = {"Authorization": f"Bearer {token}"}
    return {"base_url": METRIS_URI}, token, headers

def get_tag_values_metris(tag_id: int):
    metris_info, token, headers = get_metris_token()
    METRIS_BASE = metris_info["base_url"]
    tag_values_uri = f"{METRIS_BASE}/api/historian/v02/tagvalues"
    params = {'ids': [int(tag_id)]}
    r = requests.get(tag_values_uri, headers=headers, params=params, verify=False, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) == 0:
        raise RuntimeError("Empty response from Metris.")
    return data[0]

@app.route('/api/agent/realtime', methods=['POST'])
def agent_realtime():
    try:
        payload = request.get_json(force=True)
        q = (payload.get('query') or "").strip()
        if not q:
            return jsonify({"error":"query is required"}), 400
        # simple substring matching for safety
        matches = {}
        if q.isdigit():
            tid = int(q); matches[tid] = {"desc": desc_dict.get(tid), "score": 1.0}
        else:
            for idd, desc in desc_dict.items():
                if q in desc or desc in q:
                    matches[idd] = {"desc": desc, "score": 0.6}
        results = []; errors=[]
        for tid, info in matches.items():
            try:
                tag_val = get_tag_values_metris(tid)
                results.append({"id": tid, "desc": info.get("desc"), "score": info.get("score"),
                                "value": tag_val.get("value"), "timestamp": tag_val.get("timestamp"),
                                "quality": tag_val.get("quality"), "raw": tag_val})
            except Exception as e:
                errors.append({"id": tid, "error": str(e)})
                results.append({"id": tid, "desc": info.get("desc"), "score": info.get("score"),
                                "value": None, "error": str(e)})
        return jsonify({"matches": results, "errors": errors})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------- RAG endpoints (upload / list / query / delete) ----------------
@app.route('/api/rag/upload', methods=['POST'])
def rag_upload():
    if not RAG_AVAILABLE:
        return jsonify({"error":"RAG unavailable: missing dependencies"}), 500
    try:
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error":"upload at least one file as files[]"}), 400
        saved_paths = []
        for f in files:
            p = save_upload_file(f)
            saved_paths.append(p)
        name = request.form.get('name') or files[0].filename
        # build index (this may take time)
        with RAG_LOCK:
            index_id = build_rag_index(name=name, file_paths=saved_paths, embedding_model=AGENT_CONFIG.get('sentence_model'))
        return jsonify({"ok": True, "index_id": index_id, "name": name})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/rag/list')
def rag_list():
    out = [{"id": v["id"], "name": v["name"], "created_at": v["created_at"], "embedding_model": v.get("embedding_model")} for v in RAG_INDICES.values()]
    return jsonify(out)

@app.route('/api/rag/delete', methods=['POST'])
def rag_delete():
    try:
        payload = request.get_json(force=True)
        idx = payload.get('index_id')
        if not idx:
            return jsonify({"error":"index_id required"}), 400
        with RAG_LOCK:
            if idx in RAG_INDICES:
                # delete persisted file if exists
                path = os.path.join(RAG_STORE_DIR, f"{idx}.json")
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
                del RAG_INDICES[idx]
                return jsonify({"ok": True})
            else:
                return jsonify({"error":"index_id not found"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/rag/query', methods=['POST'])
def rag_query():
    if not RAG_AVAILABLE:
        return jsonify({"error":"RAG unavailable"}), 500
    try:
        payload = request.get_json(force=True)
        index_id = payload.get('index_id')
        question = (payload.get('question') or "").strip()
        if not index_id or not question:
            return jsonify({"error":"index_id and question required"}), 400
        top_k = int(payload.get('top_k', 3))
        try:
            matches = rag_search(index_id, question, k=top_k)
        except KeyError:
            return jsonify({"error":"index_id not found"}), 404
        # build context and call Ollama non-stream
        ctx_lines = ["检索到的知识片段："]
        for i, m in enumerate(matches, 1):
            snippet = m.get('text','')[:800]
            ctx_lines.append(f"[片段{i}] {snippet}")
        context_text = "\n\n".join(ctx_lines)
        # assemble prompt (no system prompt)
        prompt = f"参考以下知识片段回答用户问题，请在回答中标注引用片段编号：\n\n{context_text}\n\n用户问题: {question}\n\n回答："
        ollama_payload = {"model":"gemma3:4b","prompt":prompt,"max_tokens":512,"temperature":0.0,"stream":False}
        try:
            r = requests.post(OLLAMA_LOCAL, json=ollama_payload, timeout=60)
            try:
                j = r.json()
                answer = j.get('response') or j.get('text') or (j.get('output') and j.get('output')[0] and j.get('output')[0].get('content') and j.get('output')[0]['content'][0].get('text')) or json.dumps(j)
                ollama_raw = j
            except Exception:
                answer = r.text
                ollama_raw = {"raw_text": r.text}
        except Exception as e:
            traceback.print_exc()
            answer = f"Ollama call failed: {e}"
            ollama_raw = {"error": str(e)}
        short_matches = [{"id": i+1, "text": m.get('text','')[:800]} for i,m in enumerate(matches)]
        return jsonify({"matches": short_matches, "agent_answer": answer, "ollama_raw": ollama_raw})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------- Agent ask (realtime + context) ----------------
@app.route('/api/agent/ask', methods=['POST'])
def agent_ask():
    try:
        payload = request.get_json(force=True)
        q = (payload.get('query') or "").strip()
        if not q:
            return jsonify({"error":"query required"}), 400
        # match tags (simple substring)
        matches = {}
        if q.isdigit():
            tid = int(q); matches[tid] = {"desc": desc_dict.get(tid), "score":1.0}
        else:
            for idd, desc in desc_dict.items():
                if q in desc or desc in q:
                    matches[idd] = {"desc": desc, "score": 0.6}
        match_entries=[]; errors=[]
        for tid, info in matches.items():
            try:
                tag_val = get_tag_values_metris(tid)
                match_entries.append({"id": tid, "desc": info.get("desc"), "score": info.get("score"),
                                      "value": tag_val.get("value"), "timestamp": tag_val.get("timestamp"),
                                      "quality": tag_val.get("quality"), "raw": tag_val})
            except Exception as e:
                errors.append({"id": tid, "error": str(e)})
                match_entries.append({"id": tid, "desc": info.get("desc"), "score": info.get("score"),
                                      "value": None, "error": str(e)})
        # build context
        ctx_lines=["实时观测："]
        for m in match_entries:
            if m.get("value") is not None:
                ctx_lines.append(f"- ID {m['id']} ({m.get('desc')}): 值={m['value']}, 时间={m.get('timestamp')}")
            else:
                ctx_lines.append(f"- ID {m['id']} ({m.get('desc')}): 无法获取实时值 (error: {m.get('error')})")
        context_text = "\n".join(ctx_lines)
        prompt = f"参考下面实时数据回答用户问题：\n\n{context_text}\n\n用户问题: {q}\n\n请基于实时数据给出专业回答，并说明数据来源与置信度。"
        ollama_payload = {"model":"gemma3:4b","prompt":prompt,"max_tokens":512,"temperature":0.0,"stream":False}
        try:
            r = requests.post(OLLAMA_LOCAL, json=ollama_payload, timeout=60)
            try:
                j = r.json()
                agent_answer = j.get('response') or j.get('text') or (j.get('output') and j.get('output')[0] and j.get('output')[0].get('content') and j.get('output')[0]['content'][0].get('text')) or json.dumps(j)
                ollama_raw = j
            except Exception:
                agent_answer = r.text
                ollama_raw = {"raw_text": r.text}
        except Exception as e:
            traceback.print_exc()
            agent_answer = f"Ollama call failed: {e}"
            ollama_raw = {"error": str(e)}
        return jsonify({"matches": match_entries, "errors": errors, "agent_answer": agent_answer, "ollama_raw": ollama_raw})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------- Agent config endpoints (persist to config.json) ----------------
@app.route('/api/agent/config', methods=['GET', 'POST'])
def agent_config():
    global AGENT_CONFIG
    if request.method == 'GET':
        return jsonify(AGENT_CONFIG)
    else:
        try:
            payload = request.get_json(force=True)
            changed = False
            if 'sentence_model' in payload and payload['sentence_model']:
                AGENT_CONFIG['sentence_model'] = payload['sentence_model']; changed = True
            if 'threshold' in payload:
                AGENT_CONFIG['threshold'] = float(payload['threshold']); changed = True
            if 'top_k' in payload:
                AGENT_CONFIG['top_k'] = int(payload['top_k']); changed = True
            save_agent_config()
            return jsonify({"ok": True, "changed": changed, "agent_config": AGENT_CONFIG})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 400

@app.route('/api/agent/descriptions')
def agent_descriptions():
    return jsonify(desc_dict)

# ---------------- Run ----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)