import sys
import time
import os
import threading
import webbrowser
import uvicorn

# Add current directory to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app

def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8522, log_level="error")

if __name__ == "__main__":
    # 1. Start FastAPI server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(1.2)

    url = "http://127.0.0.1:8522"
    print(f"InspectMLC backend active at: {url}")

    # 2. Try launching via pywebview desktop window
    try:
        import webview
        print("Launching InspectMLC native window via pywebview (Edge Chromium)...")
        window = webview.create_window(
            title="InspectMLC - Halcyon MLC Analysis & Delivery Comparison Tool",
            url=url,
            width=1480,
            height=920,
            resizable=True,
            min_size=(1024, 700)
        )
        webview.start(gui="edgechromium")
    except Exception as err:
        print(f"Notice: pywebview window launch encountered: {err}")
        print(f"Opening InspectMLC in default web browser at {url}...")
        webbrowser.open(url)
        
        # Keep background server running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("InspectMLC shutting down.")
