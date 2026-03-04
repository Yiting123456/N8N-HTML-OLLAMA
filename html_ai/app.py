
from flask import Flask, render_template, request, Response, jsonify, stream_with_context
import threading, traceback, requests, os, sys, time

app = Flask(__name__, template_folder='templates')

DOCUMENT_PATH = r"C:\Users\fshyit02\OneDrive - ANDRITZ AG\Desktop\self-resource\MachineLearningTraining-V1.0 (2).pdf"

qa = None
qa_ready = False
qa_error = None

try:
    from lc import load_db
except Exception as e:
    load_db = None
    qa_error = f"无法导入 lc.load_db: {e}"
    print("Warning:", qa_error)
    traceback.print_exc()

def build_qa_async():
    global qa, qa_ready, qa_error
    if load_db is None:
        qa_error = qa_error or "load_db 未提供"
        return
    try:
        print("开始构建 QA 链（load_db），这可能需要较长时间...")
        qa = load_db(DOCUMENT_PATH, chain_type="stuff", k=4)
        qa_ready = True
        qa_error = None
        print("QA 构建完成。")
    except Exception as e:
        qa = None
        qa_ready = False
        qa_error = f"构建 QA 失败: {e}"
        print(qa_error)
        traceback.print_exc()

threading.Thread(target=build_qa_async, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/model')
def model_page():
    return render_template('chat.html')

@app.route('/api/status')
def status():
    return {
        "qa_ready": qa_ready,
        "qa_error": qa_error,
        "document": DOCUMENT_PATH
    }

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """
    Optional endpoint that uses langchain QA if ready.
    Body: { "question": "...", "chat_history": [...] }
    """
    global qa, qa_ready, qa_error
    try:
        data = request.get_json(force=True)
        question = data.get('question')
        chat_history = data.get('chat_history', [])
        if not question:
            return jsonify({"error": "question 不能为空"}), 400
        if not qa_ready or qa is None:
            return jsonify({"answer": None, "error": "后端 QA 未就绪: " + (qa_error or "稍后重试")}), 503

        result = qa({"question": question, "chat_history": chat_history})
        response = {
            "answer": result.get("answer"),
            "generated_question": result.get("generated_question"),
            "source_documents": []
        }
        sdocs = result.get("source_documents") or []
        for doc in sdocs:
            try:
                entry = {
                    "page_content": getattr(doc, "page_content", str(doc)),
                    "metadata": getattr(doc, "metadata", {}) or {}
                }
            except Exception:
                entry = {"raw": str(doc)}
            response["source_documents"].append(entry)
        return jsonify(response)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

OLLAMA_LOCAL = os.getenv('OLLAMA_LOCAL', 'http://127.0.0.1:11434/api/generate')

@app.route('/api/ollama/generate', methods=['POST'])
def proxy_ollama_generate():
    """
    Proxy POST to local Ollama /api/generate, preserving streaming.
    Frontend should POST JSON body like:
      { model: "gemma3:4b", prompt: "...", stream: true, ... }
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
                yield str.encode(f'\n{{"error":"proxy stream error: {e}"}}\n')
            finally:
                try:
                    resp.close()
                except:
                    pass

        return Response(stream_with_context(generate()), status=resp.status_code, content_type=resp.headers.get('Content-Type', 'application/octet-stream'))
    except requests.exceptions.RequestException as e:
        traceback.print_exc()
        return jsonify({"error": f"请求 Ollama 失败: {e}"}), 502
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)