"""
ws_mock_server.py — Day 2 test server.

Simulates the Day 3 FastAPI backend just enough to validate the frontend:
  - /ws/video  receives JPEG frame blobs and logs their size
  - /ws/audio  receives PCM chunks, logs their size, and echoes back
               100 ms of silence (so AudioPlayer gets exercised)

Usage:
    pip3 install websockets
    python3 ws_mock_server.py

Then serve the frontend in a second terminal:
    python3 -m http.server 3000 --directory frontend/

Open http://localhost:3000 in Chrome and click "Start Session".
"""

import asyncio
import websockets

PORT = 8000

SILENT_CHUNK = bytes(4800)


async def video_handler(websocket):
    frame_count = 0
    async for message in websocket:
        frame_count += 1
        size = len(message) if isinstance(message, (bytes, bytearray)) else 0
        print(f"[video] Frame #{frame_count:>4}  {size:>8,} bytes")


async def audio_handler(websocket):
    chunk_count = 0
    async for message in websocket:
        chunk_count += 1
        size = len(message) if isinstance(message, (bytes, bytearray)) else 0
        print(f"[audio] Chunk #{chunk_count:>4}  {size:>6} bytes")
        # Echo silent PCM back so the browser's AudioPlayer is exercised
        await websocket.send(SILENT_CHUNK)


async def handler(websocket):
    # websockets >= 14: path moved to websocket.request.path
    path = websocket.request.path
    print(f"[server] Client connected → {path}")

    if path == "/ws/video":
        await video_handler(websocket)
    elif path == "/ws/audio":
        await audio_handler(websocket)
    else:
        print(f"[server] Unknown path: {path} — closing.")
        await websocket.close(code=4004, reason="Unknown path")

    print(f"[server] Client disconnected ← {path}")


async def main():
    print(f"Mock WebSocket server  →  ws://localhost:{PORT}")
    print("Waiting for frontend connection…\n")
    async with websockets.serve(handler, "localhost", PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
