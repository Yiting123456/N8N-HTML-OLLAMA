
(() => {
  const messagesEl = document.getElementById('messages');
  const form = document.getElementById('composer');
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('sendBtn');
  const clearBtn = document.getElementById('clearBtn');
  const ttsToggle = document.getElementById('ttsToggle');

  let ttsEnabled = false;
  let isTyping = false;

  const OLLAMA_URL = 'http://localhost:11434/api/generate';
  const MODEL_NAME = 'gemma3:4b';

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
    return data.response || data.text || (data.output && data.output[0]?.content?.[0]?.text) || JSON.stringify(data);
  }

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

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop(); 
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
          onToken(line);
        }
      }
    }

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

  async function streamToElement(prompt, el) {
    el.textContent = ''; 
    try {
      await generateStream(prompt, chunk => {
        el.textContent += chunk;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      });
    } catch (err) {
      throw err;
    }
  }

  async function simulateBotReply(prompt) {
    if (isTyping) return;
    isTyping = true;

    const botEl = addMessage('', 'bot');

    const typingIndicator = document.createElement('span');
    typingIndicator.className = 'typing';
    typingIndicator.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    botEl.appendChild(typingIndicator);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    try {
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
      const t = botEl.querySelector('.typing');
      if (t) t.remove();
      isTyping = false;
      if (ttsEnabled && botEl.textContent) speakText(botEl.textContent);
    }
  }

  function sendMessage() {
    const txt = input.value.trim();
    if (!txt) return;
    addMessage(txt, 'user');
    input.value = '';
    fitTextarea();
    simulateBotReply(txt);
  }

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

  addMessage('你好，我是 Yiting·AI —— 已连接本地模型', 'bot');
})();