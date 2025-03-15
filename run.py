import sys
import asyncio
import argparse
import pandas as pd
from threading import Thread
import time
import traceback
import os

sys.path.append("scripts")
sys.path.append("scripts/web")
sys.path.append("scripts/dashboard")

try:
    from nyx import Nyx
    print("Imported Nyx successfully")
    from dashboard import DashboardNyx, init_dashboard, app, socketio
    print("Imported DashboardNyx, app, and socketio successfully")
except ImportError as e:
    print(f"Import error: {e}")
    traceback.print_exc()
    sys.exit(1)

def start_dashboard(host='0.0.0.0', port=5000):
    """Start the dashboard server."""
    try:
        print(f"Starting dashboard server at http://{host}:{port}")
        print(f"Open http://localhost:{port} in your browser to view the dashboard")
        socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True, debug=False)
    except Exception as e:
        print(f"Error starting dashboard server: {e}")
        traceback.print_exc()

async def run_nyx(nyx_instance, initial_input):
    """Run Nyx with the given input."""
    try:
        print(f"Handling initial input: {initial_input}")
        await nyx_instance.handle_initial_input(initial_input)
        print("Starting Nyx")
        await nyx_instance.start()
    except Exception as e:
        print(f"Error in Nyx execution: {e}")
        traceback.print_exc()
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run Nyx or Nyx with Dashboard")
    parser.add_argument("--dashboard", action="store_true", help="Run with dashboard enabled")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    # Set up debug mode if requested
    if args.debug:
        print("Debug mode enabled")
        os.environ["DEBUG"] = "1"

    try:
        initial_input = input("Enter input: ")
        if not initial_input.strip():
            print("Error: No input provided")
            sys.exit(1)

        if args.dashboard:
            print("=== Starting Nyx with Dashboard ===")
            
            # Create Nyx instance first
            print("Initializing Nyx")
            nyx = Nyx()
            
            # Initialize the dashboard with the Nyx instance
            print("Initializing DashboardNyx")
            dashboard = init_dashboard(nyx)
            
            # Start the dashboard components
            print("Starting dashboard components")
            dashboard.start()
            
            # Start the dashboard server in a separate thread
            print("Starting dashboard server thread")
            dashboard_thread = Thread(target=start_dashboard)
            dashboard_thread.daemon = True
            dashboard_thread.start()
            
            # Give the server time to start
            print("Waiting for server to start...")
            time.sleep(2)
            
            if not dashboard_thread.is_alive():
                print("Dashboard thread failed to start or crashed")
                sys.exit(1)
            print("Dashboard server is running. Open http://localhost:5000 in your browser")
            
            # Handle the input through the dashboard
            print(f"Sending input to dashboard: {initial_input}")
            dashboard.handle_input(initial_input)
            
            # Keep the main thread running
            try:
                print("Main thread waiting for dashboard to complete...")
                while dashboard_thread.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down...")
                dashboard.running = False
                time.sleep(2)  # Give time for cleanup
                sys.exit(0)
        else:
            print("=== Starting Regular Nyx ===")
            nyx = Nyx()
            asyncio.run(run_nyx(nyx, initial_input))

    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)