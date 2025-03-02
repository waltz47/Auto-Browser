import sys
import asyncio
import argparse
import pandas as pd
from threading import Thread
import time

sys.path.append("scripts")
sys.path.append("scripts/web")
sys.path.append("scripts/dashboard")

try:
    from nyx import Nyx
    print("Imported Nyx successfully")
    from dashboard import DashboardNyx, app, socketio
    print("Imported DashboardNyx, app, and socketio successfully")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

async def run_nyx(nyx_instance, initial_input):
    try:
        print(f"Handling initial input: {initial_input}")
        await nyx_instance.handle_initial_input(initial_input)
        print("Starting Nyx")
        await nyx_instance.start()
    except Exception as e:
        print(f"Error in Nyx execution: {e}")
        raise

def start_dashboard():
    try:
        print("Attempting to start Flask-SocketIO server on http://0.0.0.0:5000")
        socketio.run(app, host='127.0.0.1', port=5000, use_reloader=False, debug=True)
        print("Flask-SocketIO server running")  # This might not print due to blocking
    except Exception as e:
        print(f"Failed to start dashboard server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run Nyx or Nyx with Dashboard")
    parser.add_argument("--dashboard", action="store_true", help="Run with dashboard enabled")
    args = parser.parse_args()

    try:
        initial_input = input("Enter input: ")
        if not initial_input.strip():
            print("Error: No input provided")
            sys.exit(1)

        if args.dashboard:
            print("Initializing DashboardNyx")
            nyx = DashboardNyx()
            
            print("Starting dashboard thread")
            dashboard_thread = Thread(target=start_dashboard)
            dashboard_thread.daemon = True
            dashboard_thread.start()
            
            # Use time.sleep instead of asyncio.sleep since we're not in async context
            print("Waiting 2 seconds for server to start")
            time.sleep(2)  # Give the server time to start
            if not dashboard_thread.is_alive():
                print("Dashboard thread failed to start or crashed")
                sys.exit(1)
            print("Dashboard thread is running. Open http://localhost:5000 in your browser")
            
            asyncio.run(run_nyx(nyx, initial_input))
        else:
            print("Initializing regular Nyx")
            nyx = Nyx()
            asyncio.run(run_nyx(nyx, initial_input))

    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)