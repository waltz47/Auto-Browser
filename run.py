import os
import sys
import asyncio
import argparse
from playwright.async_api import async_playwright
import json

# Add scripts directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
from worker import Worker
from scripts.nyx import Nyx

async def run_terminal_mode():
    """Run Nyx in terminal mode."""
    nyx = Nyx()
    await nyx.setup_browser()
    worker = await nyx.create_worker()
    
    print("\nWorker initialized and ready!")
    print("Enter your task or type 'exit' to quit")

    try:
        while True:
            user_input = input("\nEnter task: ")
            if user_input.lower() == 'exit':
                break

            # Add user input to message history
            worker.messages.add_user_text(user_input)
            
            # Process task
            while True:
                active = await worker.step()
                if not active or worker.waiting_for_input:
                    break

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        await nyx.cleanup()

def run_dashboard_mode():
    """Run Nyx in dashboard mode."""
    nyx = Nyx()
    nyx.run_dashboard()

def main():
    parser = argparse.ArgumentParser(description='Run Nyx AI in terminal or dashboard mode')
    parser.add_argument('--mode', choices=['terminal', 'dashboard'], default='terminal',
                      help='Run mode: terminal or dashboard (default: terminal)')
    args = parser.parse_args()

    if args.mode == 'terminal':
        asyncio.run(run_terminal_mode())
    else:
        run_dashboard_mode()

<<<<<<< HEAD
    try:
        # In production (like Render), we don't want to prompt for input
        if os.environ.get('RENDER'):
            initial_input = "Hello! I'm ready to help."  # Default greeting
        else:
            initial_input = args.input if args.input else input("Enter input: ")
            
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
=======
if __name__ == "__main__":
    os.makedirs("log",exist_ok=True)
    main()
>>>>>>> single_agent
