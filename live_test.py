import asyncio
import os
from pathlib import Path
from google import genai
from google.genai.types import (
    LiveConnectConfig,
    SpeechConfig,
    VoiceConfig,
    PrebuiltVoiceConfig,
    Content,
    Part,
    Blob,
)

PROJECT_ID = "project-134fb569-ac25-4bca-929"     
LOCATION   = "us-central1"  

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
MODEL_ID = "gemini-live-2.5-flash-native-audio"


async def main():
    config = LiveConnectConfig(
        response_modalities=["audio"],
        speech_config=SpeechConfig(
            voice_config=VoiceConfig(
                prebuilt_voice_config=PrebuiltVoiceConfig(
                    voice_name="Aoede",
                )
            ),
        ),
    )

    print("Connecting to WhisperDev...")

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        print("Connected!\n")

        image_path = "Screenshot 2026-03-09 at 18.42.12.png"
        try:
            image_bytes = Path(image_path).read_bytes()
        except FileNotFoundError:
            print(f"Error: Could not find '{image_path}'. Make sure it's in the same folder.")
            return

        print("Sending screenshot and prompt...")

        prompt = (
            "You are WhisperDev, my expert pair programmer. "
            "Take a look at this screenshot of my terminal. "
            "What error am I getting, and how do I fix it?"
        )

        await session.send_client_content(
            turns=Content(
                role="user",
                parts=[
                    Part(inline_data=Blob(data=image_bytes, mime_type="image/jpeg")),
                    Part(text=prompt),
                ],
            )
        )

        print("Receiving audio stream", end="")

        # Output is raw PCM: 24 kHz, 16-bit, mono — no file header.
        # To play back: ffplay -f s16le -ar 24000 -ac 1 WhisperDev_response.pcm
        with open("WhisperDev_response.pcm", "wb") as f:
            async for message in session.receive():
                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            f.write(part.inline_data.data)
                            print(".", end="", flush=True)

                # Stop receiving once the model signals the turn is done
                if message.server_content and message.server_content.turn_complete:
                    break

        print("\n\nDone! Audio saved to 'WhisperDev_response.pcm'")
        print("Play it with: ffplay -f s16le -ar 24000 -ac 1 WhisperDev_response.pcm")


if __name__ == "__main__":
    asyncio.run(main())
