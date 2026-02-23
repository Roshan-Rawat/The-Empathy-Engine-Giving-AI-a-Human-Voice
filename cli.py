#!/usr/bin/env python3
"""
CLI for The Empathy Engine.
Usage: python cli.py "Your text here"
       python cli.py  (then enter text at prompt)
       python cli.py -v "Show me the SSML markup too"
"""

import argparse
import sys
from pathlib import Path

from engine import detect_emotion, text_to_speech, get_vocal_params, generate_ssml

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def main():
    parser = argparse.ArgumentParser(
        description="The Empathy Engine: emotion-aware text-to-speech."
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=None,
        help="Text to convert to speech (or omit to be prompted).",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output audio file path (default: output/empathy_<n>.wav).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show SSML markup in output.",
    )
    args = parser.parse_args()

    text = args.text
    if text is None:
        print("Enter text (Ctrl-D or Ctrl-Z to finish):")
        text = sys.stdin.read()

    if not text or not text.strip():
        print("No text provided.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.output is None:
        existing = list(OUTPUT_DIR.glob("empathy_*.wav"))
        n = len(existing) + 1
        args.output = OUTPUT_DIR / f"empathy_{n}.wav"

    print(f"Detecting emotion...")
    emotion, intensity = detect_emotion(text)
    rate_mult, vol_mult, pitch_factor = get_vocal_params(emotion, intensity)
    print(f"Emotion: {emotion} | Intensity: {intensity:.0%} | Rate x{rate_mult:.2f} | Volume x{vol_mult:.2f} | Pitch x{pitch_factor:.2f}")

    if args.verbose:
        ssml = generate_ssml(text, emotion, intensity)
        print(f"\nSSML markup:\n{ssml}\n")

    print(f"Generating audio...")

    try:
        path, _, _, _ = text_to_speech(text, args.output)
        print(f"Saved: {path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
