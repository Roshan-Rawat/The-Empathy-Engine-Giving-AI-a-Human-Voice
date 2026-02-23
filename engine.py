"""
The Empathy Engine: emotion-aware text-to-speech.
Detects sentiment, maps to vocal parameters, and generates expressive audio.

Bonus features:
  - Granular emotions (7 categories)
  - Intensity scaling (0.0-1.0)
  - SSML integration (generation, parsing, rendering)
"""

import re
import struct
import wave
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ---------------------------------------------------------------------------
# Granular emotion categories (7)
# ---------------------------------------------------------------------------
JOYFUL = "joyful"
ANGRY = "angry"
SURPRISED = "surprised"
CONCERNED = "concerned"
INQUISITIVE = "inquisitive"
SAD = "sad"
NEUTRAL = "neutral"

# Keyword sets for heuristic detection
SURPRISE_WORDS = frozenset({
    "wow", "whoa", "amazing", "incredible", "unbelievable", "omg",
    "shocked", "stunning", "astonishing", "no way", "can't believe",
    "remarkable", "extraordinary", "unexpected",
})

CONCERN_WORDS = frozenset({
    "worried", "concerned", "anxious", "uneasy", "nervous", "afraid",
    "uncertain", "hesitant", "maybe", "might", "perhaps", "careful",
    "risky", "troubling", "alarming",
})

ANGER_WORDS = frozenset({
    "angry", "furious", "frustrated", "hate", "annoyed", "outraged",
    "livid", "enraged", "infuriated", "disgusted", "fed up", "sick of",
    "terrible", "awful", "horrible",
})

SAD_WORDS = frozenset({
    "sad", "depressed", "miserable", "heartbroken", "devastated",
    "lonely", "hopeless", "gloomy", "unhappy", "sorrowful", "grief",
    "mourn", "crying", "tears", "loss", "lost",
})

# Vocal parameter defaults (pyttsx3: rate in words/min, volume 0.0-1.0)
DEFAULT_RATE = 175
DEFAULT_VOLUME = 1.0

# Emotion -> (rate_multiplier, volume_multiplier, pitch_factor) at full intensity
# pitch_factor: >1.0 = higher pitch (brighter), <1.0 = lower pitch (deeper)
EMOTION_TO_VOICE = {
    JOYFUL:      (1.45, 1.0,  1.15),   # Fast, bright
    ANGRY:       (1.30, 1.0,  0.88),   # Fast, deep/aggressive
    SURPRISED:   (1.55, 1.0,  1.22),   # Fastest, highest pitch
    CONCERNED:   (0.78, 0.80, 0.94),   # Slow, soft, slightly low
    INQUISITIVE: (0.88, 0.90, 1.10),   # Moderate, rising intonation feel
    SAD:         (0.60, 0.70, 0.84),   # Very slow, quiet, deep
    NEUTRAL:     (1.00, 1.0,  1.00),   # Default
}


# ---------------------------------------------------------------------------
# Emotion detection (granular, with intensity)
# ---------------------------------------------------------------------------

def _has_keyword(text_lower: str, keywords: frozenset) -> bool:
    """Check if any keyword appears in text."""
    return any(kw in text_lower for kw in keywords)


def detect_emotion(text: str) -> tuple[str, float]:
    """
    Classify text into one of 7 emotions and return intensity (0.0-1.0).

    Returns (emotion, intensity) where intensity = abs(compound).
    """
    if not text or not text.strip():
        return NEUTRAL, 0.0

    text = text.strip()
    analyzer = SentimentIntensityAnalyzer()
    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]
    neg = scores["neg"]
    pos = scores["pos"]
    intensity = min(abs(compound), 1.0)

    text_lower = text.lower()
    has_question = "?" in text
    has_exclamation = "!" in text
    has_caps = len(re.findall(r"[A-Z]{2,}", text)) >= 1

    # Inquisitive: question marks dominate
    if has_question and not has_exclamation:
        return INQUISITIVE, max(intensity, 0.3)

    # Angry: strong negative + exclamation/caps
    if compound <= -0.3 and (has_exclamation or has_caps) or _has_keyword(text_lower, ANGER_WORDS):
        if neg > 0.2 or _has_keyword(text_lower, ANGER_WORDS):
            return ANGRY, max(intensity, 0.5)

    # Surprised: high compound + surprise keywords (checked before joyful)
    if abs(compound) >= 0.3 and _has_keyword(text_lower, SURPRISE_WORDS):
        return SURPRISED, max(intensity, 0.5)

    # Joyful: strong positive + exclamation
    if compound >= 0.3 and (has_exclamation or has_caps):
        return JOYFUL, max(intensity, 0.5)

    # Joyful: positive sentiment
    if compound >= 0.05:
        if _has_keyword(text_lower, SURPRISE_WORDS):
            return SURPRISED, max(intensity, 0.4)
        return JOYFUL, intensity

    # Sad: negative without anger markers
    if compound <= -0.05:
        if _has_keyword(text_lower, SAD_WORDS):
            return SAD, max(intensity, 0.4)
        if _has_keyword(text_lower, CONCERN_WORDS):
            return CONCERNED, max(intensity, 0.3)
        return SAD, intensity

    # Concerned: mild negative + hedging words
    if _has_keyword(text_lower, CONCERN_WORDS):
        return CONCERNED, max(intensity, 0.2)

    return NEUTRAL, intensity


# ---------------------------------------------------------------------------
# Intensity scaling
# ---------------------------------------------------------------------------

def scale_multiplier(base: float, intensity: float) -> float:
    """
    Scale a vocal multiplier by intensity.
    At intensity=0 -> 1.0 (neutral), at intensity=1 -> full base multiplier.
    """
    return 1.0 + (base - 1.0) * intensity


def get_vocal_params(emotion: str, intensity: float = 1.0) -> tuple[float, float, float]:
    """Return (rate_multiplier, volume_multiplier, pitch_factor) scaled by intensity."""
    base_rate, base_vol, base_pitch = EMOTION_TO_VOICE.get(emotion, EMOTION_TO_VOICE[NEUTRAL])
    return (
        scale_multiplier(base_rate, intensity),
        scale_multiplier(base_vol, intensity),
        scale_multiplier(base_pitch, intensity),
    )


# ---------------------------------------------------------------------------
# SSML integration
# ---------------------------------------------------------------------------

def generate_ssml(text: str, emotion: str, intensity: float) -> str:
    """
    Generate an SSML string for the given text, emotion, and intensity.

    Uses <prosody> for rate/pitch/volume, <emphasis> for strong emotions,
    and <break> for pauses suited to the emotion.
    """
    rate_mult, vol_mult, pitch_factor = get_vocal_params(emotion, intensity)

    # Map multiplier to SSML rate percentage
    rate_pct = f"{int(rate_mult * 100)}%"
    volume_map = {
        (0.0, 0.85): "soft",
        (0.85, 0.93): "medium",
        (0.93, 1.01): "default",
        (1.01, 2.0): "loud",
    }
    volume_label = "default"
    for (lo, hi), label in volume_map.items():
        if lo <= vol_mult < hi:
            volume_label = label
            break

    # Pitch adjustment based on emotion
    pitch_map = {
        JOYFUL: "+10%", ANGRY: "-5%", SURPRISED: "+15%",
        CONCERNED: "-3%", INQUISITIVE: "+5%", SAD: "-10%",
        NEUTRAL: "+0%",
    }
    pitch = pitch_map.get(emotion, "+0%")

    # Emphasis level
    emphasis = "strong" if intensity >= 0.7 else "moderate" if intensity >= 0.4 else "none"

    # Break time for emotional pauses
    break_map = {
        JOYFUL: "200ms", ANGRY: "100ms", SURPRISED: "300ms",
        CONCERNED: "400ms", SAD: "500ms", INQUISITIVE: "250ms",
        NEUTRAL: "200ms",
    }
    break_time = break_map.get(emotion, "200ms")

    # Build SSML
    lines = ['<speak>']
    lines.append(f'  <prosody rate="{rate_pct}" volume="{volume_label}" pitch="{pitch}">')

    if emphasis != "none":
        lines.append(f'    <emphasis level="{emphasis}">{text}</emphasis>')
    else:
        lines.append(f'    {text}')

    lines.append('  </prosody>')
    lines.append(f'  <break time="{break_time}"/>')
    lines.append('</speak>')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SSML parsing and segment rendering
# ---------------------------------------------------------------------------

@dataclass
class SpeechSegment:
    """A segment of speech with its own vocal parameters."""
    text: str
    rate_mult: float
    vol_mult: float
    pause_ms: int = 0  # silence after this segment


def parse_ssml_segments(ssml: str, base_rate_mult: float, base_vol_mult: float) -> list[SpeechSegment]:
    """
    Parse an SSML string into a list of SpeechSegments.
    Each segment carries its own rate/volume multipliers and optional pause.
    """
    segments: list[SpeechSegment] = []

    try:
        root = ET.fromstring(ssml)
    except ET.ParseError:
        # Fallback: return a single segment with the raw text
        text = re.sub(r"<[^>]+>", "", ssml).strip()
        if text:
            segments.append(SpeechSegment(text=text, rate_mult=base_rate_mult, vol_mult=base_vol_mult))
        return segments

    def _parse_rate(rate_str: str) -> float:
        """Convert SSML rate string (e.g. '120%') to multiplier."""
        if rate_str.endswith("%"):
            return float(rate_str[:-1]) / 100.0
        return base_rate_mult

    def _parse_volume(vol_str: str) -> float:
        """Convert SSML volume label to multiplier."""
        vol_map = {"silent": 0.0, "x-soft": 0.3, "soft": 0.6, "medium": 0.8,
                   "default": 1.0, "loud": 1.1, "x-loud": 1.2}
        return vol_map.get(vol_str, base_vol_mult)

    def _walk(element, rate: float, vol: float):
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

        if tag == "break":
            time_str = element.get("time", "200ms")
            ms = int(re.sub(r"[^0-9]", "", time_str)) if time_str else 200
            segments.append(SpeechSegment(text="", rate_mult=rate, vol_mult=vol, pause_ms=ms))
            return

        cur_rate, cur_vol = rate, vol
        if tag == "prosody":
            if element.get("rate"):
                cur_rate = _parse_rate(element.get("rate"))
            if element.get("volume"):
                cur_vol = _parse_volume(element.get("volume"))

        # Collect direct text
        if element.text and element.text.strip():
            segments.append(SpeechSegment(text=element.text.strip(), rate_mult=cur_rate, vol_mult=cur_vol))

        for child in element:
            _walk(child, cur_rate, cur_vol)
            # Tail text after child element
            if child.tail and child.tail.strip():
                segments.append(SpeechSegment(text=child.tail.strip(), rate_mult=cur_rate, vol_mult=cur_vol))

    _walk(root, base_rate_mult, base_vol_mult)
    return segments


def _shift_pitch(wav_path: Path, factor: float) -> None:
    """
    Shift pitch of a WAV file by modifying its sample rate (stdlib only).
    factor > 1.0 = higher pitch (brighter), < 1.0 = lower pitch (deeper).
    This also changes playback speed proportionally — for TTS this is desirable
    as it creates distinctly different voice characters per emotion.
    """
    if abs(factor - 1.0) < 0.02:
        return
    with wave.open(str(wav_path), "rb") as r:
        params = r.getparams()
        frames = r.readframes(params.nframes)
    new_rate = int(params.framerate * factor)
    with wave.open(str(wav_path), "wb") as w:
        w.setparams(params._replace(framerate=new_rate))
        w.writeframes(frames)


# ---------------------------------------------------------------------------
# Main TTS function
# ---------------------------------------------------------------------------

def text_to_speech(text: str, output_path: str | Path) -> tuple[str, str, float, str]:
    """
    Convert text to speech with emotion-based vocal modulation.

    Applies three distinct vocal parameters:
      1. Rate (speaking speed via pyttsx3)
      2. Volume (loudness via pyttsx3)
      3. Pitch (post-processing via WAV sample-rate shift)

    Returns (path, emotion, intensity, ssml).
    """
    import pyttsx3

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    emotion, intensity = detect_emotion(text)
    rate_mult, vol_mult, pitch_factor = get_vocal_params(emotion, intensity)
    ssml = generate_ssml(text, emotion, intensity)

    # Ensure .wav extension for compatibility
    if output_path.suffix.lower() not in (".wav", ".mp3"):
        output_path = output_path.with_suffix(".wav")

    # Synthesize with pyttsx3 (rate + volume)
    engine = pyttsx3.init()
    engine.setProperty("rate", int(DEFAULT_RATE * rate_mult))
    engine.setProperty("volume", min(1.0, DEFAULT_VOLUME * vol_mult))
    engine.save_to_file(text, str(output_path))
    engine.runAndWait()

    # Post-process: pitch shift via WAV sample-rate modification (stdlib only)
    try:
        if output_path.is_file() and output_path.stat().st_size > 0:
            _shift_pitch(output_path, pitch_factor)
    except Exception:
        pass  # pitch shift is best-effort; rate+volume still applied

    return str(output_path), emotion, intensity, ssml
