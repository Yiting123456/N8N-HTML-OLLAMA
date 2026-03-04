
const express = require('express');
const fetch = global.fetch || require('node-fetch'); 
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

    res.status(r.status);
    for (const [k, v] of r.headers) {
      res.setHeader(k, v);
    }
    r.body.pipe(res);
  } catch (err) {
    console.error('Proxy error:', err);
    res.status(500).json({ error: String(err) });
  }
});

app.listen(3000, () => console.log('Proxy running on http://localhost:3000'));