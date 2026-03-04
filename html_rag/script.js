// script.js — 使用本地 Ollama (gemma3:4b) 的流式 API 集成示例
(() => {
  const messagesEl = document.getElementById('messages');
  const form = document.getElementById('composer');
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('sendBtn');
  const clearBtn = document.getElementById('clearBtn');
  const ttsToggle = document.getElementById('ttsToggle');

  let ttsEnabled = false;
  let isTyping = false;

  // 配置：本地 Ollama endpoint 与模型（已设置为你指定的 gemma3:4b）
  const OLLAMA_URL = 'http://localhost:11434/api/generate';
  const MODEL_NAME = 'gemma3:4b';

  // UI helpers
  function fitTextarea() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  }
  input.addEventListener('input', fitTextarea);
  window.addEventListener('load', fitTextarea);

  function addMessage(content, who = 'bot', opts = {}) {
    const el = document.createElement('div');
    el.className = 'msg ' + who;
    if (opts.html) el.innerHTML = content;
    else el.textContent = content;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight - messagesEl.clientHeight;
    return el;
  }

  // 非流式生成（fallback 或 测试用）
  async function generateOnce(prompt) {
    const payload = {
      model: MODEL_NAME,
      prompt,
      max_tokens: 512,
      temperature: 0.2,
      stream: false
    };
    const res = await fetch(OLLAMA_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error('Ollama error: ' + res.status + ' ' + txt);
    }
    const data = await res.json();
    // 兼容不同返回字段
    return data.response || data.text || (data.output && data.output[0]?.content?.[0]?.text) || JSON.stringify(data);
  }

  // 流式生成（推荐：用于实时输出/打字效果）
  async function generateStream(prompt, onToken) {
    const payload = {
      model: MODEL_NAME,
      prompt,
      max_tokens: 1024,
      temperature: 0.2,
      stream: true
    };

    const res = await fetch(OLLAMA_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error('Ollama error: ' + res.status + ' ' + txt);
    }

    // 浏览器 readable stream 逐块读取
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Ollama 常以 NDJSON / 每行 JSON 返回多个 chunk，按行解析
      const lines = buffer.split('\n');
      buffer = lines.pop(); // 保留不完整行
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const obj = JSON.parse(line);
          const text =
            obj.response ||
            obj.text ||
            obj.output?.[0]?.content?.[0]?.text ||
            (obj.choices && obj.choices[0] && (obj.choices[0].delta?.content || obj.choices[0].text)) ||
            obj.token ||
            '';
          if (text) onToken(text);
        } catch (e) {
          // 若不是 JSON，直接作为原始文本片段输出
          onToken(line);
        }
      }
    }

    // 处理最后残余缓冲
    if (buffer.trim()) {
      try {
        const obj = JSON.parse(buffer);
        const text = obj.response || obj.text || '';
        if (text) onToken(text);
      } catch (e) {
        onToken(buffer);
      }
    }
  }

  // 把流式输出附加到单个消息元素
  async function streamToElement(prompt, el) {
    // 首先显示一个 typing 占位光标样式（如果需要）
    el.textContent = ''; // 清空以便流式填充
    try {
      await generateStream(prompt, chunk => {
        el.textContent += chunk;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      });
    } catch (err) {
      throw err;
    }
  }

  // 主回复流程：优先使用流式，失败则回退非流式
  async function simulateBotReply(prompt) {
    if (isTyping) return;
    isTyping = true;

    // 创建 bot 气泡并立即显示占位（可为打字点或空）
    const botEl = addMessage('', 'bot');

    // small UX: show tiny typing indicator until first token arrives
    const typingIndicator = document.createElement('span');
    typingIndicator.className = 'typing';
    typingIndicator.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    botEl.appendChild(typingIndicator);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    try {
      // 使用流式
      await streamToElement(prompt, botEl);
    } catch (errStream) {
      console.warn('Stream failed, falling back to non-stream:', errStream);
      try {
        const full = await generateOnce(prompt);
        botEl.textContent = full;
      } catch (errOnce) {
        console.error('Non-stream also failed:', errOnce);
        botEl.textContent = '抱歉，模型调用失败：' + (errOnce.message || errOnce);
      }
    } finally {
      // 移除 typing indicator（如果还在）
      const t = botEl.querySelector('.typing');
      if (t) t.remove();
      isTyping = false;
      if (ttsEnabled && botEl.textContent) speakText(botEl.textContent);
    }
  }

  // 发送消息逻辑
  function sendMessage() {
    const txt = input.value.trim();
    if (!txt) return;
    addMessage(txt, 'user');
    input.value = '';
    fitTextarea();
    simulateBotReply(txt);
  }

  // 事件绑定
  sendBtn.addEventListener('click', sendMessage);
  clearBtn.addEventListener('click', () => {
    messagesEl.innerHTML = '';
    addMessage('会话已清空。你好，未来。', 'bot');
  });

  form.addEventListener('submit', e => {
    e.preventDefault();
    sendMessage();
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  ttsToggle.addEventListener('click', () => {
    ttsEnabled = !ttsEnabled;
    ttsToggle.setAttribute('aria-pressed', String(ttsEnabled));
    ttsToggle.style.opacity = ttsEnabled ? '1' : '0.7';
  });

  function speakText(text) {
    if (!('speechSynthesis' in window)) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'zh-CN';
    utter.rate = 1;
    utter.pitch = 1;
    speechSynthesis.cancel();
    speechSynthesis.speak(utter);
  }

  // （可选）保留或初始化背景 Canvas 的原实现（若你有 canvas 脚本，将其放回）
  addMessage('你好，我是 Neon·AI —— 已连接本地模型 gemma3:4b。', 'bot');
})();