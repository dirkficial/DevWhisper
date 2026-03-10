Run the DevWhisper test suite.

## Python tests (WebSocket server behavior)

Run from the project root:

```bash
cd /Users/derekkim/Desktop/DevWhisper && /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m pytest tests/python/test_ws_server.py -v
```

These 9 tests cover WebSocket routing, SILENT_CHUNK format, audio echo, unknown path rejection, and simultaneous connections. They run in ~0.4s with no API calls.

## Python tests (Gemini Live API — costs quota)

Only run when explicitly needed to verify API health:

```bash
GOOGLE_CLOUD_PROJECT=project-134fb569-ac25-4bca-929 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m pytest tests/python/test_live_api.py -v -s
```

## Browser/JS tests (PCM audio math)

Start a static server and open the test page:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m http.server 3000 --directory /Users/derekkim/Desktop/DevWhisper
```

Then open http://localhost:3000/tests/browser/test.html in Chrome.

These 15 assertions cover int16↔float32 conversion and PCM downsampling math.
