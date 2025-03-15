import os
from flask import Flask, render_template
from flask_socketio import SocketIO
import asyncio
import base64
from io import BytesIO
import time
from threading import Thread, Lock
from queue import Queue
import traceback
from functools import partial

# Import your Nyx class
from nyx import Nyx

# Create global instances
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class DashboardNyx:
    _instance = None
    _nyx = None
    
    @classmethod
    def initialize(cls, nyx_instance=None):
        """Initialize or get the DashboardNyx instance.
        
        Args:
            nyx_instance: Optional Nyx instance. If not provided, will create a new one.
            
        Returns:
            DashboardNyx: The dashboard instance
        """
        if cls._instance is None:
            if nyx_instance is None:
                nyx_instance = Nyx()
            cls._instance = cls(nyx_instance)
        return cls._instance
    
    @classmethod
    def get_instance(cls):
        """Get the current DashboardNyx instance.
        
        Returns:
            DashboardNyx: The current dashboard instance or None if not initialized
        """
        return cls._instance
    
    def __init__(self, nyx_instance=None):
        """Initialize the dashboard with a Nyx instance.
        
        Args:
            nyx_instance: An instance of the Nyx class to monitor. If None, will use existing or create new.
        """
        if DashboardNyx._instance is not None:
            raise RuntimeError("DashboardNyx instance already exists. Use initialize() or get_instance()")
        
        DashboardNyx._instance = self
        self.nyx = nyx_instance if nyx_instance is not None else DashboardNyx._nyx
        if self.nyx is None:
            self.nyx = Nyx()
        DashboardNyx._nyx = self.nyx
        
        self.emit_lock = Lock()
        self.request_queue = Queue()
        self.running = True
        self.event_loop = None
        self.input_handler_thread = None
        self.state_emission_thread = None
        
        # Register routes
        @app.route('/')
        def index():
            return render_template('index.html')
        
        @socketio.on('connect')
        def handle_connect():
            print('Client connected')
            with self.emit_lock:
                self.emit_state()
    
    async def initialize_nyx(self):
        """Initialize Nyx components including browser and other required setup."""
        try:
            # Initialize browser and other components through handle_initial_input
            if hasattr(self.nyx, 'handle_initial_input'):
                if asyncio.iscoroutinefunction(self.nyx.handle_initial_input):
                    await self.nyx.handle_initial_input("")  # Empty input to just initialize
                else:
                    self.nyx.handle_initial_input("")
                print("Nyx components initialized successfully")
            else:
                print("Warning: Nyx instance does not have handle_initial_input method")
                
        except Exception as e:
            print(f"Error initializing Nyx components: {e}")
            traceback.print_exc()
            raise
    
    def start(self):
        """Start the dashboard and all its components."""
        try:
            # Create new event loop for async operations
            self.event_loop = asyncio.new_event_loop()
            
            # Start input handler thread
            self.input_handler_thread = Thread(target=self._run_input_handler)
            self.input_handler_thread.daemon = True
            self.input_handler_thread.start()
            
            # Start state emission thread
            self.state_emission_thread = Thread(target=self._run_state_emission)
            self.state_emission_thread.daemon = True
            self.state_emission_thread.start()
            
            print("Dashboard components started successfully")
        except Exception as e:
            print(f"Error starting dashboard components: {e}")
            traceback.print_exc()
            raise
    
    def _run_input_handler(self):
        """Run the input handler loop in its own thread."""
        try:
            print("Starting input handler thread")
            # Set up event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            while self.running:
                try:
                    if not self.request_queue.empty():
                        input_text = self.request_queue.get()
                        print(f"Input handler received: {input_text}")
                        
                        if input_text.lower() == 'quit':
                            self.running = False
                            print("Received quit command, shutting down")
                            break
                        
                        print(f"Processing input in handler: {input_text}")
                        # Run the coroutine in this thread's event loop
                        try:
                            loop.run_until_complete(self.handle_initial_input(input_text))
                            print("Input processing completed successfully")
                        except Exception as e:
                            print(f"Error in input processing: {e}")
                            traceback.print_exc()
                        
                    # Keep the thread running even after processing input
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Error processing input: {e}")
                    traceback.print_exc()
            
            print("Input handler thread exiting")
        except Exception as e:
            print(f"Fatal error in input handler thread: {e}")
            traceback.print_exc()
        finally:
            loop.close()
            print("Input handler event loop closed")
    
    def _run_state_emission(self):
        """Run the state emission loop in its own thread."""
        while self.running:
            try:
                with self.emit_lock:
                    self.emit_state()
                time.sleep(1)
            except Exception as e:
                print(f"Error in state emission: {e}")
                traceback.print_exc()
    
    async def handle_initial_input(self, input_text):
        """Handle the initial input by creating agents and distributing tasks.
        
        Args:
            input_text: The input text containing the task description
        """
        try:
            print(f"=== Starting handle_initial_input with: {input_text} ===")
            
            # Initialize Nyx components first
            print("Initializing Nyx components...")
            await self.initialize_nyx()
            print("Nyx components initialized")
            
            # Let Nyx handle the input directly
            if hasattr(self.nyx, 'handle_initial_input'):
                print("Calling Nyx's handle_initial_input method")
                if asyncio.iscoroutinefunction(self.nyx.handle_initial_input):
                    print("Calling async handle_initial_input")
                    await self.nyx.handle_initial_input(input_text)
                else:
                    print("Calling sync handle_initial_input")
                    self.nyx.handle_initial_input(input_text)
                print("Nyx handle_initial_input completed")
                    
                # Start Nyx processing if needed
                if hasattr(self.nyx, 'start'):
                    print("Starting Nyx processing")
                    if asyncio.iscoroutinefunction(self.nyx.start):
                        print("Calling async start")
                        await self.nyx.start()
                    else:
                        print("Calling sync start")
                        self.nyx.start()
                        
                print("Nyx processing started successfully")
            else:
                print("Error: Nyx instance does not have required methods")
                
            print("=== Completed handle_initial_input ===")
        except Exception as e:
            print(f"Error in handle_initial_input: {e}")
            traceback.print_exc()
            raise
    
    def emit_state(self):
        """Emit the current state of all workers and tasks."""
        if not self.nyx:
            return
            
        try:
            state = {
                'workers': [],
                'tasks': [],
                'dependencies': []
            }
            
            # Safely collect worker states
            if hasattr(self.nyx, 'workers'):
                for worker_id, worker in enumerate(self.nyx.workers):
                    if worker:
                        worker_state = {
                            'id': worker_id,
                            'task': worker.current_task if hasattr(worker, 'current_task') else 'Unknown',
                            'status': 'error' if (hasattr(worker, 'error_state') and worker.error_state) 
                                     else ('active' if (hasattr(worker, 'is_running') and worker.is_running) 
                                          else 'idle'),
                            'error': worker.error_state if hasattr(worker, 'error_state') else None
                        }
                        state['workers'].append(worker_state)
            
            # Safely collect task information
            if hasattr(self.nyx, 'results'):
                for worker_id, result in self.nyx.results.items():
                    if isinstance(result, dict):
                        task_state = {
                            'id': f'task_{worker_id}',
                            'worker_id': worker_id,
                            'description': result.get('task', 'Unknown task'),
                            'status': result.get('status', 'unknown'),
                            'error': result.get('error_message') if result.get('status') == 'error' else None
                        }
                        state['tasks'].append(task_state)
            
            # Safely collect dependencies
            if hasattr(self.nyx, 'task_dependencies'):
                for task_id, deps in self.nyx.task_dependencies.items():
                    if isinstance(deps, (list, tuple)):
                        for dep_id in deps:
                            state['dependencies'].append({
                                'from': f'task_{dep_id}',
                                'to': f'task_{task_id}'
                            })
            
            socketio.emit('state_update', state)
        except Exception as e:
            print(f"Error collecting or emitting state: {e}")
            traceback.print_exc()
    
    def handle_input(self, input_text):
        """Handle input by adding it to the request queue."""
        if not input_text:
            return
        print(f"Adding input to queue: {input_text}")
        self.request_queue.put(input_text)
        print("Input added to queue successfully")
    
    def run(self, host='localhost', port=5000):
        """Run the dashboard server."""
        try:
            print(f"Starting dashboard components...")
            self.start()
            print(f"Dashboard running at http://{host}:{port}")
            socketio.run(app, host=host, port=port)
        except Exception as e:
            print(f"Error running dashboard: {e}")
            traceback.print_exc()
        finally:
            print("Dashboard shutting down, cleaning up resources...")
            self.running = False
            
            # Clean up browser resources
            try:
                if hasattr(self.nyx, 'context') and self.nyx.context:
                    print("Closing browser context...")
                    cleanup_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(cleanup_loop)
                    cleanup_loop.run_until_complete(self.nyx.context.close())
                    print("Browser context closed")
                    
                if hasattr(self.nyx, 'browser') and self.nyx.browser:
                    print("Closing browser...")
                    if not cleanup_loop.is_closed():
                        cleanup_loop.run_until_complete(self.nyx.browser.close())
                    else:
                        cleanup_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(cleanup_loop)
                        cleanup_loop.run_until_complete(self.nyx.browser.close())
                    print("Browser closed")
                    
                if hasattr(self.nyx, 'playwright') and self.nyx.playwright:
                    print("Stopping Playwright...")
                    if not cleanup_loop.is_closed():
                        cleanup_loop.run_until_complete(self.nyx.playwright.stop())
                    else:
                        cleanup_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(cleanup_loop)
                        cleanup_loop.run_until_complete(self.nyx.playwright.stop())
                    print("Playwright stopped")
                    
                if 'cleanup_loop' in locals() and not cleanup_loop.is_closed():
                    cleanup_loop.close()
            except Exception as e:
                print(f"Error during browser cleanup: {e}")
                traceback.print_exc()
            
            # Close event loop
            if self.event_loop and not self.event_loop.is_closed():
                self.event_loop.close()
                
            print("Dashboard shutdown complete")

# Helper functions for initialization
def init_dashboard(nyx_instance=None):
    """Initialize the dashboard with an optional Nyx instance.
    
    Args:
        nyx_instance: Optional Nyx instance. If not provided, will create a new one.
        
    Returns:
        DashboardNyx: The initialized dashboard instance
    """
    return DashboardNyx.initialize(nyx_instance)

def get_dashboard():
    """Get the current dashboard instance.
    
    Returns:
        DashboardNyx: The current dashboard instance or None if not initialized
    """
    return DashboardNyx.get_instance()
