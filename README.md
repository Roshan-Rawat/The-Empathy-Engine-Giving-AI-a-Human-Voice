# The Empathy Engine

Emotion-aware text-to-speech: the service analyzes the sentiment of input text, maps it to vocal parameters (rate and volume), and generates a playable audio file so the voice matches the mood.

## Features

- **Text input** via CLI or REST API (and optional web UI).
- **Emotion detection**: classifies text into **7 granular emotions** using VADER sentiment + keyword heuristics.
- **Vocal parameter modulation**: adjusts **rate** (speed), **volume**, and **pitch** of the synthesized speech — three distinct vocal parameters.
- **Intensity scaling**: emotion strength (0.0–1.0) proportionally scales vocal modulation.
- **SSML generation**: produces valid SSML markup with `<prosody>`, `<emphasis>`, and `<break>` tags.
- **Audio output**: playable `.wav` files with pitch post-processing via stdlib `wave`.

## Setup

1. **Clone or download** this repository and go into the project folder:
   ```bash
   cd Darwix
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run** via CLI or web app (see below).

## How to Run

### CLI

```bash
# With text as argument
python cli.py "This is the best news ever!"

# Interactive: type or paste text, then Ctrl-D (Mac/Linux) or Ctrl-Z (Windows)
python cli.py

# Custom output path
python cli.py "I'm so frustrated." -o my_audio.wav

# Verbose mode: show SSML markup
python cli.py -v "This is amazing!"
```

Generated files are saved under `output/` by default (e.g. `output/empathy_1.wav`).

### Web UI and API

```bash
flask --app app run
# or: python app.py
```

- Open **http://127.0.0.1:5000** in a browser: enter text, click "Generate speech," and play the result. The UI shows an **intensity bar** and a collapsible **SSML markup** section.
- **API**: `POST /api/speak` with JSON body `{ "text": "Your text here" }`. Response includes `emotion`, `intensity`, `ssml`, and a URL to the generated audio file.

## Design Choices

### Emotion detection (7 categories)

- **VADER** (Valence Aware Dictionary and sEntiment Reasoner) provides a `compound` score in `[-1, 1]` plus component scores (`pos`, `neg`, `neu`).
- Additional heuristics layer on top of VADER:
  - **`?`** marks → **inquisitive**
  - Strong negative + `!`/CAPS or anger keywords → **angry**
  - Strong positive + `!`/CAPS → **joyful**
  - High compound + surprise keywords → **surprised**
  - Negative + sadness keywords → **sad**
  - Mild negative + hedging/concern keywords → **concerned**
  - Low compound → **neutral**

### Emotion-to-voice mapping

| Emotion | Rate | Volume | Pitch | Character |
|---------|------|--------|-------|-----------|
| joyful | x1.45 | x1.00 | x1.15 | Fast, bright |
| angry | x1.30 | x1.00 | x0.88 | Fast, deep/aggressive |
| surprised | x1.55 | x1.00 | x1.22 | Fastest, highest pitch |
| concerned | x0.78 | x0.80 | x0.94 | Slow, soft, slightly low |
| inquisitive | x0.88 | x0.90 | x1.10 | Moderate, rising intonation feel |
| sad | x0.60 | x0.70 | x0.84 | Very slow, quiet, deep |
| neutral | x1.00 | x1.00 | x1.00 | Default delivery |

Multipliers shown at full intensity (1.0). At lower intensities, all three values scale toward 1.0 (neutral).

We modulate **three distinct vocal parameters**: rate (pyttsx3), volume (pyttsx3), and pitch (post-processing via WAV sample-rate shift using stdlib `wave`).

### TTS engine

- **pyttsx3** is used for offline, local synthesis with controllable rate and volume. No API keys are required. On macOS it uses the system voice (e.g. Siri voices if available).
- **Pitch shifting** is applied as a post-processing step using the stdlib `wave` module — the WAV sample rate is modified to shift pitch up or down, creating distinctly different voice characters per emotion without any external dependencies.

## Bonus Features

### 1. Granular Emotions

Expanded from 3 categories (positive/negative/neutral) to 7 distinct emotions: **joyful**, **angry**, **surprised**, **concerned**, **inquisitive**, **sad**, and **neutral**. Detection uses a combination of VADER compound/component scores, punctuation heuristics (`?`, `!`, ALL CAPS), and keyword-based frozensets for surprise, concern, anger, and sadness.

### 2. Intensity Scaling

Each detected emotion now carries an **intensity** value from 0.0 to 1.0 (derived from `abs(compound)`). Vocal parameters scale proportionally: at intensity 0 the voice is neutral, at intensity 1 the full emotion-specific modulation is applied. Formula: `scaled = 1.0 + (base - 1.0) * intensity`.

### 3. SSML Integration

The engine generates valid SSML markup for each utterance:
- **`<prosody>`** — rate, volume, and pitch based on emotion + intensity
- **`<emphasis>`** — `strong` (intensity >= 0.7) or `moderate` (>= 0.4)
- **`<break>`** — emotion-appropriate pauses (e.g. 500ms for sad, 100ms for angry)

SSML is parsed back into `SpeechSegment` objects for structured representation of the speech output. Audio is rendered via pyttsx3 (rate + volume) with pitch post-processing via stdlib `wave`.

## Requirements Met

| Requirement | Implementation |
|-------------|----------------|
| Text input | CLI argument/prompt and `POST /api/speak` |
| Emotion detection (>= 3 categories) | 7 granular emotions via VADER + heuristics |
| >= 2 vocal parameters | Rate, volume, and pitch (intensity-scaled) |
| Emotion-to-voice mapping | Table in `engine.py`: `EMOTION_TO_VOICE` |
| Playable audio output | `.wav` via pyttsx3 `save_to_file` |
| **Bonus: Granular emotions** | 7 emotions with keyword + punctuation heuristics |
| **Bonus: Intensity scaling** | 0.0–1.0 proportional modulation |
| **Bonus: SSML integration** | Generate, parse, and render SSML markup |
| **Bonus: Web UI** | Flask app at `http://127.0.0.1:5000` |

## License

MIT.
