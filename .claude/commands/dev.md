Start the DevWhisper development server.

Kill anything running on port 8000, then start the FastAPI backend (which also serves the frontend) using the explicit Python path:

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null; echo "Port cleared"
```

Then start the server from the backend directory:

```bash
cd /Users/derekkim/Desktop/DevWhisper/backend && GOOGLE_CLOUD_PROJECT=project-134fb569-ac25-4bca-929 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m uvicorn main:app --reload --port 8000
```

Once running, the app is available at http://localhost:8000. The frontend is served by FastAPI — no separate static server needed.

Remind the user to open http://localhost:8000 in Chrome (not Safari — AudioWorklet requires Chrome).
