"""
Flask API and web UI for The Empathy Engine.
Run: flask --app app run
"""

import subprocess
import sys
import time
import uuid
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template_string

from engine import detect_emotion, get_vocal_params, generate_ssml

app = Flask(__name__)
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>The Empathy Engine</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 560px;
      margin: 2rem auto;
      padding: 0 1rem;
      background: #0f0f12;
      color: #e4e4e7;
    }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    .sub { color: #71717a; font-size: 0.9rem; margin-bottom: 1.5rem; }
    textarea {
      width: 100%;
      min-height: 120px;
      padding: 0.75rem;
      border: 1px solid #3f3f46;
      border-radius: 8px;
      background: #18181b;
      color: #e4e4e7;
      font-size: 1rem;
      resize: vertical;
    }
    textarea:focus { outline: none; border-color: #6366f1; }
    button {
      margin-top: 0.75rem;
      padding: 0.6rem 1.2rem;
      background: #6366f1;
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      cursor: pointer;
    }
    button:hover { background: #4f46e5; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .result {
      margin-top: 1.5rem;
      padding: 1rem;
      background: #18181b;
      border-radius: 8px;
      border: 1px solid #3f3f46;
    }
    .emotion-label {
      font-weight: 600;
      margin-bottom: 0.5rem;
      font-size: 1.05rem;
    }
    .intensity-bar-container {
      margin: 0.75rem 0;
    }
    .intensity-label {
      font-size: 0.85rem;
      color: #a1a1aa;
      margin-bottom: 0.3rem;
    }
    .intensity-bar {
      height: 8px;
      border-radius: 4px;
      background: #27272a;
      overflow: hidden;
    }
    .intensity-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.4s ease;
    }
    audio { width: 100%; margin-top: 0.75rem; }
    .error { color: #f87171; margin-top: 1rem; }
    details {
      margin-top: 0.75rem;
      background: #1e1e22;
      border: 1px solid #3f3f46;
      border-radius: 6px;
      padding: 0.5rem 0.75rem;
    }
    details summary {
      cursor: pointer;
      color: #a1a1aa;
      font-size: 0.85rem;
      user-select: none;
    }
    details pre {
      margin: 0.5rem 0 0;
      padding: 0.5rem;
      background: #0f0f12;
      border-radius: 4px;
      font-size: 0.8rem;
      color: #a5b4fc;
      overflow-x: auto;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <h1>The Empathy Engine</h1>
  <p class="sub">Enter text. We detect emotion and speak it with matching tone.</p>
  <form id="form">
    <textarea name="text" placeholder="e.g. This is the best news ever! Or: I'm really frustrated with this." required></textarea>
    <button type="submit" id="btn">Generate speech</button>
  </form>
  <div id="result"></div>
  <script>
    const EMOTION_COLORS = {
      joyful: '#facc15', angry: '#ef4444', surprised: '#f97316',
      concerned: '#a78bfa', inquisitive: '#38bdf8', sad: '#60a5fa',
      neutral: '#a1a1aa'
    };

    function escapeHtml(str) {
      const d = document.createElement('div');
      d.textContent = str;
      return d.innerHTML;
    }

    document.getElementById('form').onsubmit = async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btn');
      const result = document.getElementById('result');
      const text = document.querySelector('textarea').value.trim();
      if (!text) return;
      btn.disabled = true;
      result.innerHTML = '<p>Generating...</p>';
      try {
        const r = await fetch('/api/speak', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Failed');
        const audioUrl = '/output/' + encodeURIComponent(data.filename) + '?t=' + (data.timestamp || Date.now());
        const mime = data.filename.toLowerCase().endsWith('.mp3') ? 'audio/mpeg' : 'audio/wav';
        const color = EMOTION_COLORS[data.emotion] || EMOTION_COLORS.neutral;
        const pct = Math.round((data.intensity || 0) * 100);
        const ssmlBlock = data.ssml
          ? `<details>
               <summary>View SSML markup</summary>
               <pre>${escapeHtml(data.ssml)}</pre>
             </details>`
          : '';
        result.innerHTML = `
          <div class="result">
            <div class="emotion-label" style="color:${color}">Detected emotion: ${escapeHtml(data.emotion)}</div>
            <div class="intensity-bar-container">
              <div class="intensity-label">Intensity: ${pct}%</div>
              <div class="intensity-bar">
                <div class="intensity-fill" style="width:${pct}%;background:${color}"></div>
              </div>
            </div>
            <audio controls preload="auto" type="${mime}"></audio>
            <p class="error" style="display:none;margin-top:0.5rem">Audio could not load. Try opening the file from the output folder.</p>
            ${ssmlBlock}
          </div>
        `;
        const audio = result.querySelector('audio');
        const errMsg = result.querySelector('.error');
        try {
          const res = await fetch(audioUrl);
          if (!res.ok) throw new Error('Failed to load audio');
          const blob = await res.blob();
          audio.src = URL.createObjectURL(blob);
          audio.onerror = () => { errMsg.style.display = 'block'; };
        } catch (e) {
          errMsg.style.display = 'block';
        }
      } catch (err) {
        result.innerHTML = '<p class="error">' + escapeHtml(err.message) + '</p>';
      }
      btn.disabled = false;
    };
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


def _run_tts_subprocess(text: str, output_path: Path) -> None:
    """Run TTS in a subprocess so it works reliably when Flask runs in a thread."""
    script = f"""
from pathlib import Path
from engine import text_to_speech
text_to_speech({repr(text)}, {repr(str(output_path))})
"""
    r = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parent),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout or "TTS subprocess failed")


def _convert_to_browser_friendly(path: Path) -> Path | None:
    """
    Convert TTS WAV to MP3 if ffmpeg is available. Returns .mp3 path or None.
    """
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(str(path), format="wav")
        seg = seg.set_frame_rate(22050).set_channels(1)
        mp3_path = path.with_suffix(".mp3")
        seg.export(str(mp3_path), format="mp3", bitrate="128k")
        if mp3_path.is_file() and mp3_path.stat().st_size > 0:
            return mp3_path
    except Exception:
        pass
    return None


def _generate_mp3_with_gtts(text: str, output_path: Path) -> bool:
    """Generate MP3 with gTTS (works without ffmpeg). Returns True if successful."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(str(output_path))
        return output_path.is_file() and output_path.stat().st_size > 0
    except Exception:
        return False


@app.route("/api/speak", methods=["POST"])
def api_speak():
    """Accept JSON { \"text\": \"...\" }, return emotion, intensity, ssml, and filename."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Missing or empty 'text'"}), 400
    try:
        emotion, intensity = detect_emotion(text)
        ssml = generate_ssml(text, emotion, intensity)
        base_id = uuid.uuid4().hex
        wav_path = OUTPUT_DIR / f"{base_id}.wav"
        _run_tts_subprocess(text, wav_path)
        if not wav_path.is_file() or wav_path.stat().st_size == 0:
            return jsonify({"error": "Audio file was not generated"}), 500
        serve_path = _convert_to_browser_friendly(wav_path)
        if serve_path is None:
            mp3_path = OUTPUT_DIR / f"{base_id}.mp3"
            if _generate_mp3_with_gtts(text, mp3_path):
                serve_path = mp3_path
            else:
                serve_path = wav_path
        filename = serve_path.name
        return jsonify({
            "emotion": emotion,
            "intensity": round(intensity, 3),
            "ssml": ssml,
            "filename": filename,
            "timestamp": int(time.time() * 1000),
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Speech generation timed out"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/output/<filename>")
def output_file(filename):
    if "/" in filename or "\\" in filename:
        return "", 404
    path = OUTPUT_DIR / filename
    if not path.is_file():
        return "", 404
    mimetype = "audio/mpeg" if filename.lower().endswith(".mp3") else "audio/wav"
    return send_file(
        path,
        mimetype=mimetype,
        as_attachment=False,
        conditional=False,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
