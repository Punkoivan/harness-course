"""Push-to-talk voice client for kagent's voice-router agent.

Enter -> record (parecord) -> Enter again -> stop -> transcribe (Google
Cloud Speech-to-Text) -> send to voice-router over A2A (message/send) ->
speak the reply (Google Cloud Text-to-Speech + ffplay).
See course task 5 / voice-agent/README.md.

Requires GOOGLE_APPLICATION_CREDENTIALS pointing at a service-account key
with Speech-to-Text and Text-to-Speech API access. Deliberately NOT copied
into this repo -- point it at wherever you keep it, e.g.:

    export GOOGLE_APPLICATION_CREDENTIALS=~/Downloads/your-key.json

Usage:
    uv run voice_client.py
"""

import os
import subprocess
import sys
import tempfile
import uuid

import requests
from google.cloud import speech, texttospeech

AGENT_URL = "http://localhost:8182/"  # port-forward: kagent svc/voice-router 8182:8080


def record() -> str:
    path = tempfile.mktemp(suffix=".wav")
    input("Press Enter to start recording...")
    proc = subprocess.Popen(
        ["parecord", "--channels=1", "--rate=16000", "--file-format=wav", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    input("Recording... press Enter to stop.")
    proc.terminate()
    proc.wait()
    return path


def transcribe(wav_path: str) -> str:
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("GOOGLE_APPLICATION_CREDENTIALS is not set.", file=sys.stderr)
        sys.exit(1)
    client = speech.SpeechClient()
    with open(wav_path, "rb") as f:
        content = f.read()
    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="uk-UA",
    )
    response = client.recognize(config=config, audio=audio)
    if not response.results:
        return ""
    return response.results[0].alternatives[0].transcript


def ask_agent(text: str) -> str:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }
    # Delegation (voice-router -> k8s-agent -> back) means 2-3+ full LLM
    # turns on a shared, single-slot (--parallel 1) CPU model -- each turn
    # alone has taken 100-230s in practice (see ADR-0005/ADR-0003). 300s
    # wasn't enough for the full chain; give it real headroom.
    resp = requests.post(AGENT_URL, json=msg, timeout=1200)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["result"]["artifacts"][0]["parts"][0]["text"]
    except (KeyError, IndexError):
        try:
            return data["result"]["status"]["message"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return f"(couldn't parse agent reply: {data})"


def speak(text: str) -> None:
    client = texttospeech.TextToSpeechClient()
    synth_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="uk-UA", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    response = client.synthesize_speech(
        input=synth_input, voice=voice, audio_config=audio_config
    )
    mp3_path = tempfile.mktemp(suffix=".mp3")
    with open(mp3_path, "wb") as f:
        f.write(response.audio_content)
    subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path])
    os.remove(mp3_path)


def main() -> None:
    print("Voice client for voice-router. Ctrl+C to quit.\n")
    while True:
        try:
            wav_path = record()
        except KeyboardInterrupt:
            print()
            break

        print("Transcribing...")
        text = transcribe(wav_path)
        os.remove(wav_path)
        if not text:
            print("(no speech recognized)\n")
            continue
        print(f"You said: {text}")

        print("Asking voice-router... if this delegates to another agent,")
        print("expect several minutes (shared single-slot CPU model, ADR-0005).")
        reply = ask_agent(text)
        print(f"Agent: {reply}\n")

        speak(reply)


if __name__ == "__main__":
    main()
