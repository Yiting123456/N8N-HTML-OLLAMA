// server.js — 简单的 Express 代理，转发到本地 Ollama（保留流）
const express = require('express');
const fetch = global.fetch || require('node-fetch'); // Node 18+ 自带 fetch
const app = express();
app.use(express.json());

const OLLAMA = 'http://localhost:11434/api/generate';
const MODEL = 'gemma3:4b';

app.post('/api/ollama/generate', async (req, res) => {
  try {
    const body = {
      model: MODEL,
      prompt: req.body.prompt || req.body.input || '',
      stream: !!req.body.stream,
      max_tokens: req.body.max_tokens ?? 1024,
      temperature: req.body.temperature ?? 0.2
    };

    const r = await fetch(OLLAMA, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    // 转发状态与头
    res.status(r.status);
    for (const [k, v] of r.headers) {
      // 可过滤掉某些 header，如果需要
      res.setHeader(k, v);
    }
    // 将 Ollama 的响应 body 直接 pipe 回前端（保留流式）
    r.body.pipe(res);
  } catch (err) {
    console.error('Proxy error:', err);
    res.status(500).json({ error: String(err) });
  }
});

app.listen(3000, () => console.log('Proxy running on http://localhost:3000'));