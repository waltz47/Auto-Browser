import os
import asyncio
from playwright.async_api import async_playwright
from worker import Worker
import json
from openai import AsyncOpenAI
from fastapi import FastAPI, WebSocket, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
import numpy as np
from PIL import Image
import io
from pydantic import BaseModel
import weakref

class Nyx:
    def __init__(self):
        """Initialize Nyx with basic configuration."""
        # Create required directories
        self._create_required_directories()

        # Load configuration
        with open("api_config.cfg", 'r') as f:
            cfg = f.read()

        self.config = {}
        for line in cfg.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                self.config[key.strip()] = value.strip().strip('"')

        # Determine API type
        if os.environ.get("OPENAI_API_KEY") is not None:
            self.api = "openai"
            self.MODEL = self.config["openai_model"]
        elif os.environ.get("XAI_API_KEY") is not None:
            self.api = "xai"
            self.MODEL = self.config["xai_model"]
        else:
            self.api = "ollama"
            self.MODEL = self.config["ollama_local_model"]

        self.tools = None #worker can initialize directly
        
        # Initialize video streaming attributes
        self.video_track = None
        self.pc = None
        self.stream_task = None
        
        # Initialize FastAPI app
        self.app = FastAPI()
        self.setup_routes()

        # Initialize Playwright resources
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.worker = None
        
        # Track active WebSocket connection
        self._active_websocket = None

    def _create_required_directories(self):
        """Create required directories if they don't exist."""
        required_dirs = ['static', 'templates']
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if not dir_path.exists():
                dir_path.mkdir(parents=True)
                print(f"Created directory: {dir_path}")
        
        # Check if dashboard template exists
        template_path = Path("templates/dashboard.html")
        if not template_path.exists():
            print(f"Warning: Dashboard template not found at {template_path}")
            print("Please ensure dashboard.html exists in the templates directory")

    def setup_routes(self):
        """Set up FastAPI routes."""
        from fastapi import Body
        from pydantic import BaseModel
        
<<<<<<< HEAD
        # Get planning response from API
        planning_prompt = f"""Given the following task, create a plan with agents to perform the tasks as required.
        Keep the breakdown minimal and focused, and consolidate tasks intelligently.
        
        Task: {initial_input}
        
        Respond with a JSON object in this format:
        {{
            "tasks": [
                {{"task": "First subtask description", "dependencies": []}},
                {{"task": "Second subtask description", "dependencies": [0]}},
                {{"task": "Third subtask description that depends on first and second", "dependencies": [0, 1]}}
            ]
        }}
        
        IMPORTANT GUIDELINES:
        1. CONSOLIDATE RELATED ACTIONS INTO SINGLE TASKS. Do not split tasks that can logically be done by the same agent.
           Examples of tasks that should be combined into ONE task:
           - "Search for a hotel and book a room" (NOT two separate tasks)
           - "Find a restaurant and make a reservation" (NOT two separate tasks)
           - "Research a topic and write a summary" (NOT two separate tasks)
           - "Navigate to a website and fill out a form" (NOT two separate tasks)
           
        2. Only create separate tasks when they:
           - Require fundamentally different capabilities
           - Need to be executed in parallel
           - Depend on information that must be gathered by different agents
           
        3. Make tasks comprehensive - each task should include all related steps a single agent could reasonably perform.
        
        4. Only create dependencies when a task genuinely cannot begin until another task is completed.
        
        5. Keep the total number of tasks to the absolute minimum necessary.
        
        6. Dependencies should be listed as indices of previous tasks (zero-based).
        """
        
        try:
            print("Sending planning request to API...")
            planning_response = await self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": self.NYX_PROMPT},
                    {"role": "user", "content": planning_prompt}
                ],
                temperature=0.2  # Lower temperature for more focused task planning
=======
        class RTCOffer(BaseModel):
            sdp: str
            type: str

        # Mount static files
        self.app.mount("/static", StaticFiles(directory="static"), name="static")

        # Setup routes
        @self.app.get("/")
        async def get():
            template_path = Path("templates/dashboard.html")
            if not template_path.exists():
                return HTMLResponse("Error: Dashboard template not found. Please ensure dashboard.html exists in the templates directory.")
            return HTMLResponse(template_path.read_text())

        @self.app.post("/offer")
        async def offer(params: RTCOffer):
            from aiortc import RTCPeerConnection, RTCSessionDescription
            import json

            offer = RTCSessionDescription(
                sdp=params.sdp,
                type=params.type
>>>>>>> single_agent
            )

            pc = RTCPeerConnection()
            self.pc = pc  # Store reference to peer connection

            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                if pc.connectionState == "failed":
                    await pc.close()
                    self.pc = None

            # Create and add video track
            if not self.video_track:
                self.video_track = await self.create_video_track()
            pc.addTrack(self.video_track)

            # Handle the offer
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            # Check if we already have an active connection
            if self._active_websocket is not None:
                try:
                    await websocket.accept()
                    # Send a special message to trigger page refresh on the client side
                    await websocket.send_text("__REFRESH_PAGE__")
                    await websocket.close(code=1000, reason="Another connection is already active")
                except:
                    pass
                return

            await websocket.accept()
            self._active_websocket = websocket
            
            try:
                # Initialize browser if needed
                if not self.page:
                    await self.setup_browser()

                # Initialize or update worker
                worker = await self.create_worker(websocket)
                
<<<<<<< HEAD
                task_plan = json.loads(plan_text)
                raw_tasks = task_plan.get('tasks', [])
                
                # Process tasks - no filtering based on task type
                tasks = []
                seen_task_descriptions = set()
                
                for task in raw_tasks:
                    # Extract task description
                    task_desc = task['task'].strip()
                    
                    # Skip empty tasks
                    if not task_desc:
                        continue
                        
                    # Skip duplicate tasks
                    task_lower = task_desc.lower()
                    if task_lower in seen_task_descriptions:
                        continue
                    seen_task_descriptions.add(task_lower)
                    
                    # Add task with original description
                    tasks.append({
                        "task": task_desc,
                        "dependencies": task.get('dependencies', [])
                    })
                
                # Apply task consolidation to reduce unnecessary agents
                tasks = self._consolidate_tasks(tasks)
                print(f"Successfully parsed and consolidated to {len(tasks)} tasks from plan")
            except json.JSONDecodeError:
                print("Error parsing task plan JSON, using single task")
                tasks = [{"task": initial_input, "dependencies": []}]
            
            # Create an agent for each task
            created_workers = []
            task_to_worker_id = {}  # Map task indices to worker IDs for dependency resolution
            
            for i, task in enumerate(tasks):
                print(f"Creating agent for task {i+1}/{len(tasks)}: {task['task']}")
                
                # Convert task index dependencies to worker ID dependencies
                worker_dependencies = []
                for dep in task.get("dependencies", []):
                    if isinstance(dep, int) and dep in task_to_worker_id:
                        worker_dependencies.append(task_to_worker_id[dep])
                
                # Create the agent with resolved dependencies
                worker_id = await self.create_agent(
                    task_description=task["task"],
                    dependencies=worker_dependencies
                )
                
                # Store the mapping from task index to worker ID
                task_to_worker_id[i] = worker_id
                created_workers.append(worker_id)
                print(f"Created agent {worker_id} for task: {task['task']}")
                
                # Add task to input queue
                if worker_id in self.input_queues:
                    print(f"Adding task to input queue for worker {worker_id}")
                    await self.input_queues[worker_id].put(task["task"])
                else:
                    print(f"Warning: No input queue found for worker {worker_id}")
            
            print(f"All {len(created_workers)} agents created and tasks assigned")
            
            # Start worker tasks
            for worker_id in created_workers:
                print(f"Starting task for Worker {worker_id}")
                # Create a new task for the worker and store it
                worker_task = asyncio.create_task(self.run_worker(self.workers[worker_id]))
                self.worker_tasks[worker_id] = worker_task
                print(f"Task created and started for Worker {worker_id}")
                await asyncio.sleep(0.1)
            
            print("All worker tasks started successfully")
            
        except Exception as e:
            print(f"Error creating agents: {e}")
            traceback.print_exc()
            raise
            
        print("=== Completed handle_initial_input ===")

    async def execute_command(self, function_name, args):
        """Execute a command based on the function name and arguments."""
        try:
            if function_name == "create_csv":
                self.create_csv(args['filename'], args['tasks'])
            elif function_name == "use_csv":
                self.use_csv(args['filename'])
            elif function_name == "create_agent":
                await self.create_agent(
                    task_description=args['task_description'],
                    dependencies=args.get('dependencies', [])  # Use get() with default empty list
                )
            elif function_name == "destroy_agent":
                await self.destroy_agent(args['worker_id'])
            else:
                print(f"Unknown command: {function_name}")
        except Exception as e:
            print(f"Error executing command {function_name}: {e}")
            raise

    def create_csv(self, filename, tasks):
        filename = os.path.join("input", filename)
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['tasks'])
            for task in tasks:
                writer.writerow([task])
        print(f"CSV file '{filename}' created with tasks: {tasks}")
        self.use_csv(filename)

    def use_csv(self, filename):
        df = pd.read_csv(filename)
        self.input_list = list(df['tasks'])
        print(f"Tasks loaded from CSV file '{filename}': {self.input_list}")

        self.MAX_MESSAGES = 100
        self.num_workers = len(self.input_list)
        self.request_queue = Queue()
        self.workers = []
        self.worker_tasks = {}
        self.input_queues = {}
        print(f"Nyx initialized with {self.num_workers} workers")

    def on_browser_disconnected(self):
        print("Browser disconnected. Exiting program.")
        sys.exit(0)

    async def create_agent(self, task_description: str, dependencies: list = None) -> int:
        """Create a new agent for a specific task."""
        try:
            # Ensure dependencies is a list
            if dependencies is None:
                dependencies = []
            elif not isinstance(dependencies, list):
                dependencies = [dependencies]
                
            # Convert any non-integer dependencies to their worker IDs if possible
            resolved_dependencies = []
            for dep in dependencies:
                if isinstance(dep, int):
                    # Validate worker ID exists
                    if 0 <= dep < len(self.workers) and self.workers[dep] is not None:
                        resolved_dependencies.append(dep)
                else:
                    # Dependency is not an integer - might be a task description or other identifier
                    # This could be enhanced in the future if needed
                    print(f"Warning: Non-integer dependency {dep} skipped")
                    
            # Find the next available worker ID
            worker_id = len(self.workers)
            if self.available_worker_ids:
                worker_id = min(self.available_worker_ids)
                self.available_worker_ids.remove(worker_id)

            print(f"Creating agent {worker_id} for task: {task_description}")
            print(f"Agent dependencies: {resolved_dependencies}")

            # Create new browser page
            try:
                if worker_id > 0:
                    print(f"Creating new page for worker {worker_id}")
                    page = await self.context.new_page()
                else:
                    print(f"Using existing page for worker {worker_id}")
                    page = self.page
                print(f"Browser page created for agent {worker_id}")
            except Exception as e:
                print(f"Error creating browser page: {e}")
                traceback.print_exc()
                raise

            # Initialize worker
            try:
                # Import web tools from tools.py
                from tools import functions as web_tools
                
                # Combine web tools with orchestration tools from tools.json if worker is the main orchestrator
                combined_tools = web_tools
                if worker_id == 0:  # Assuming worker 0 is the main orchestrator
                    combined_tools = self.tools + web_tools
                    print(f"Worker {worker_id} (orchestrator) initialized with {len(combined_tools)} tools")
                else:
                    print(f"Worker {worker_id} initialized with {len(web_tools)} web tools")
                
                worker = Worker(
                    page=page,
                    worker_id=worker_id,
                    request_queue=self.request_queue,
                    api=self.api,
                    model=self.MODEL,
                    max_messages=self.MAX_MESSAGES,
                    tools=combined_tools  # Pass combined tools to worker
                )
                worker.enable_vision = self.config.get("enable_vision", False)
                worker.current_task = task_description
                worker.waiting_for_input = True  # Set waiting for input flag
                worker.first_run_complete = False  # Initialize first run flag
                print(f"Worker {worker_id} initialized")
            except Exception as e:
                print(f"Error initializing worker: {e}")
                traceback.print_exc()
                raise

            # Set up queues and dependencies
            try:
                # Ensure workers list is long enough
                while len(self.workers) <= worker_id:
                    self.workers.append(None)
                    
                self.workers[worker_id] = worker
                self.input_queues[worker_id] = asyncio.Queue()
                self.error_queues[worker_id] = asyncio.Queue()
                worker.set_queues(self.input_queues[worker_id], self.error_queues[worker_id])
                
                # Set up task dependencies
                if resolved_dependencies:
                    self.task_dependencies[worker_id] = resolved_dependencies
                    print(f"Worker {worker_id} depends on workers: {resolved_dependencies}")
                
                # Initialize results entry
                self.results[worker_id] = {
                    'task': task_description,
                    'status': 'initializing',
                    'dependencies': resolved_dependencies,
                    'last_action': None
                }
                
                print(f"Queues and dependencies set for worker {worker_id}")
            except Exception as e:
                print(f"Error setting up worker queues: {e}")
                traceback.print_exc()
                raise

            # Initialize API client
            try:
                await worker.setup_client()
                print(f"API client initialized for worker {worker_id}")
            except Exception as e:
                print(f"Error initializing API client: {e}")
                traceback.print_exc()
                raise

            print(f"Agent {worker_id} created successfully")
            return worker_id

        except Exception as e:
            print(f"Error creating agent: {e}")
            traceback.print_exc()
            if 'worker_id' in locals() and worker_id not in self.available_worker_ids:
                self.available_worker_ids.add(worker_id)
            raise

    async def destroy_agent(self, worker_id: int):
        """Destroy an agent and clean up its resources."""
        try:
            print(f"Destroying agent {worker_id}")
            
            if worker_id in self.worker_tasks:
                # Cancel the worker's task
                print(f"Cancelling worker {worker_id} task")
                self.worker_tasks[worker_id].cancel()
                
                # Close the browser page (but not for worker 0 which uses the initial page)
                if worker_id > 0 and self.workers[worker_id] and hasattr(self.workers[worker_id], 'page'):
                    print(f"Closing page for worker {worker_id}")
                    await self.workers[worker_id].page.close()
                
                # Clean up resources
                print(f"Cleaning up resources for worker {worker_id}")
                self.workers[worker_id] = None
                self.available_worker_ids.add(worker_id)
                
                if worker_id in self.input_queues:
                    del self.input_queues[worker_id]
                if worker_id in self.error_queues:
                    del self.error_queues[worker_id]
                if worker_id in self.worker_tasks:
                    del self.worker_tasks[worker_id]
                    
                print(f"Agent {worker_id} destroyed successfully")
            else:
                print(f"No task found for worker {worker_id}, nothing to destroy")
        except Exception as e:
            print(f"Error destroying agent {worker_id}: {e}")
            traceback.print_exc()

    async def get_agent_results(self, worker_id: int) -> dict:
        """Get the results from a specific agent."""
        return self.results.get(worker_id, {})

    async def run_worker(self, worker):
        """Enhanced worker execution with result tracking."""
        print(f"Starting worker {worker.worker_id} execution")
        try:
            # Initialize the worker's API client if not already done
            if worker.client is None:
                print(f"Initializing API client for worker {worker.worker_id}")
                await worker.setup_client()
            
            # Check if dependencies are met before starting
            if worker.worker_id in self.task_dependencies:
                deps = self.task_dependencies[worker.worker_id]
                print(f"Worker {worker.worker_id} waiting for dependencies: {deps}")
                
                # Update status to waiting for dependencies
                self.results[worker.worker_id] = {
                    'task': worker.current_task,
                    'status': 'waiting_for_dependencies',
                    'dependencies': deps,
                    'last_action': f"Waiting for tasks {deps} to complete"
                }
                
                # Poll for dependency completion
                while True:
                    deps_completed = all(
                        self.results.get(dep_id, {}).get('status') == 'completed'
                        for dep_id in deps
                    )
                    if deps_completed:
                        print(f"Worker {worker.worker_id} dependencies satisfied")
                        break
                    
                    # Check if any dependency has errored out
                    deps_errored = any(
                        self.results.get(dep_id, {}).get('status') == 'error'
                        for dep_id in deps
                    )
                    if deps_errored:
                        error_deps = [dep_id for dep_id in deps 
                                     if self.results.get(dep_id, {}).get('status') == 'error']
                        error_msg = f"Dependencies for worker {worker.worker_id} have errors: {error_deps}"
                        print(error_msg)
                        raise Exception(error_msg)
                        
                    print(f"Worker {worker.worker_id} waiting for dependencies {deps}")
                    await asyncio.sleep(1)
            
            # Update status to active
            self.results[worker.worker_id] = {
                'task': worker.current_task,
                'status': 'active',
                'last_action': 'Starting worker execution'
            }
            
            # Main worker loop
            while True:
                print(f"Worker {worker.worker_id} executing step")
                active = await worker.step()
                
                # Store results
                if active:
                    # Get the most recent message content
                    last_message = None
                    if hasattr(worker, 'messages') and worker.messages.messages:
                        last_messages = [msg for msg in worker.messages.messages if msg.role == 'assistant']
                        if last_messages:
                            last_message = last_messages[-1].content
                    
                    self.results[worker.worker_id] = {
                        'task': worker.current_task,
                        'status': 'active',
                        'last_action': last_message or "Processing task"
                    }
                else:
                    self.results[worker.worker_id] = {
                        'task': worker.current_task,
                        'status': 'completed',
                        'last_action': "Task completed successfully",
                        'completion_time': time.time()
                    }
                    print(f"Worker {worker.worker_id} has completed its task")
                    break
                    
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            print(f"Worker {worker.worker_id} task was cancelled")
            self.results[worker.worker_id] = {
                'task': worker.current_task,
                'status': 'cancelled',
                'error': 'Task was cancelled',
                'error_time': time.time()
            }
        except Exception as e:
            print(f"Worker {worker.worker_id} error: {e}")
            traceback.print_exc()
            self.results[worker.worker_id] = {
                'task': worker.current_task,
                'status': 'error',
                'error_message': str(e),
                'error_time': time.time()
            }
        
        print(f"Worker {worker.worker_id} execution completed")
        return worker.worker_id

    async def handle_input_requests(self):
        """Handle input requests from workers asynchronously."""
        print("Starting input request handler")
        while True:
            await asyncio.sleep(0.1)
            try:
                while not self.request_queue.empty():
=======
                try:
                    print("\n=== Nyx AI Initialized ===")
                    print("Worker initialized and ready!")
                    await websocket.send_text("\nAuto Browser is ready. Enter your task below.\n")
                except RuntimeError:
                    return

                while True:
>>>>>>> single_agent
                    try:
                        # Get message from websocket
                        data = await websocket.receive_text()
                        
                        try:
                            await websocket.send_text(f"\nUser: {data}\n")
                            print(f"\n=== User Input ===\n{data}")
                            
                            # Process the task with planning
                            active = await worker.process_user_input(data)
                            if active:
                                # Process the planned steps
                                while True:
                                    active = await worker.step()
                                    if not active:
                                        print("\n=== Ready for Next Input ===")
                                        break

                        except RuntimeError as e:
                            if "Connection closed" in str(e):
                                break
                            raise

                    except RuntimeError as e:
                        if "Connection closed" in str(e):
                            break
                        raise
                    except Exception as e:
                        error_msg = f"Error processing message: {str(e)}"
                        print(f"\n=== Error ===\n{error_msg}")
                        try:
                            await websocket.send_text(f"\nAn error occurred: {error_msg}")
                        except:
                            pass
                        break

            except Exception as e:
                error_msg = f"WebSocket error: {str(e)}"
                print(f"\n=== Error ===\n{error_msg}")
            finally:
                # Clean up worker reference and active websocket
                if self.worker:
                    self.worker.websocket = None
                if self._active_websocket == websocket:
                    self._active_websocket = None
                print("WebSocket connection closed")

    async def setup_browser(self):
        """Initialize browser and create a page."""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,  # Run in headless mode
                args=[
                    "--ignore-certificate-errors",
                    "--disable-extensions",
                    "--disable-blink-features=AutomationControlled",
                    "--window-size=1920,1080"  # Set window size
                ]
            )
            
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},  # Increased viewport size to 1080p
                screen={"width": 1920, "height": 1080},  # Match screen size with viewport
                permissions=["geolocation"],
            )
            
            self.page = await self.context.new_page()
            await self.page.goto("about:blank")  # Navigate to a blank page to ensure page is ready

    async def get_video_frame(self):
        """Capture current page as video frame."""
        if self.page:
            screenshot = await self.page.screenshot(type='jpeg', quality=80)
            return screenshot
        return None

    async def create_video_track(self):
        """Create a VideoStreamTrack from browser page."""
        from aiortc.mediastreams import MediaStreamTrack
        import av
        import fractions
        import asyncio
        import numpy as np
        from PIL import Image
        import io
        import weakref
        
        class BrowserVideoStreamTrack(MediaStreamTrack):
            kind = "video"

            def __init__(self, nyx_instance):
                super().__init__()
                self.nyx = weakref.ref(nyx_instance)  # Weak reference to avoid circular reference
                self._frame_count = 0
                self._stopped = False

            async def recv(self):
                if self._stopped:
                    return None

                try:
                    nyx = self.nyx()
                    if nyx is None or nyx.page is None:
                        raise ValueError("Page is not available")

                    screenshot = await nyx.page.screenshot(type='jpeg', quality=80)
                    if screenshot is None:
                        raise ValueError("Failed to capture screenshot")

                    # Convert screenshot to numpy array
                    image = Image.open(io.BytesIO(screenshot))
                    frame_data = np.array(image)
                    
                    # Create video frame
                    frame = av.VideoFrame.from_ndarray(frame_data, format='rgb24')
                    frame.pts = self._frame_count
                    frame.time_base = fractions.Fraction(1, 30)  # 30 fps
                    self._frame_count += 1
                    return frame

                except Exception as e:
                    print(f"Error capturing frame: {e}")
                    # Return a blank frame on error
                    blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                    frame = av.VideoFrame.from_ndarray(blank_frame, format='rgb24')
                    frame.pts = self._frame_count
                    frame.time_base = fractions.Fraction(1, 30)
                    self._frame_count += 1
                    return frame

            async def stop(self):
                self._stopped = True
                await super().stop()

        # Create and return the video track
        return BrowserVideoStreamTrack(self)

    async def create_worker(self, websocket=None) -> Worker:
        """Create and initialize a single worker."""
        if not self.worker:
            # Convert string 'true'/'false' to boolean
            enable_vision = self.config.get("enable_vision", "false").lower() == "true"
            
            self.worker = Worker(
                page=self.page,
                worker_id=0,
                request_queue=None,
                api=self.api,
                model=self.MODEL,
                max_messages=100,
                tools=self.tools,
                websocket=websocket,
                enable_vision=enable_vision  # Pass the vision flag
            )
            await self.worker.setup_client()
        else:
            self.worker.websocket = websocket
        return self.worker

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection."""
        # Check if we already have an active connection
        if self._active_websocket is not None:
            try:
                await websocket.close(code=1000, reason="Another connection is already active")
            except:
                pass
            return

        await websocket.accept()
        self._active_websocket = websocket
        
        try:
            # Initialize browser if needed
            if not self.page:
                await self.setup_browser()

            # Initialize or update worker
            worker = await self.create_worker(websocket)
            
            try:
                print("\n=== Nyx AI Initialized ===")
                print("Worker initialized and ready!")
                await websocket.send_text("\nAuto Browser is ready. Enter your task below.\n")
            except RuntimeError:
                return

            while True:
                try:
                    # Get message from websocket
                    data = await websocket.receive_text()
                    
                    try:
                        await websocket.send_text(f"\nUser: {data}\n")
                        print(f"\n=== User Input ===\n{data}")
                        
                        # Process the task with planning
                        active = await worker.process_user_input(data)
                        if active:
                            # Process the planned steps
                            while True:
                                active = await worker.step()
                                if not active:
                                    print("\n=== Ready for Next Input ===")
                                    break

                    except RuntimeError as e:
                        if "Connection closed" in str(e):
                            break
                        raise

                except RuntimeError as e:
                    if "Connection closed" in str(e):
                        break
                    raise
                except Exception as e:
                    error_msg = f"Error processing message: {str(e)}"
                    print(f"\n=== Error ===\n{error_msg}")
                    try:
                        await websocket.send_text(f"\nAn error occurred: {error_msg}")
                    except:
                        pass
                    break

        except Exception as e:
            error_msg = f"WebSocket error: {str(e)}"
            print(f"\n=== Error ===\n{error_msg}")
        finally:
<<<<<<< HEAD
            print("Nyx execution completed, cleaning up resources")
            # Don't close browser here - let the dashboard handle it
            # This prevents premature browser closure
            # if hasattr(self, 'browser'):
            #     await self.browser.close()
            # if hasattr(self, 'playwright'):
            #     await self.playwright.stop()
            # print("Browser and Playwright stopped")
            
        print("Nyx system execution completed")

    def _consolidate_tasks(self, tasks):
        """Consolidate related tasks that could be handled by a single agent.
        
        This reduces the number of agents by combining tasks that:
        1. Have a direct dependency relationship
        2. Are sequential and closely related
        3. Don't have incoming dependencies from other tasks
        """
        if not tasks or len(tasks) <= 1:
            return tasks
            
        print("Starting task consolidation...")
        
        # Create a dependency graph
        depends_on = {}  # task_idx -> list of task indices it depends on
        depended_by = {}  # task_idx -> list of task indices that depend on it
        
        for i, task in enumerate(tasks):
            depends_on[i] = task.get('dependencies', [])
            for dep in task.get('dependencies', []):
                if dep not in depended_by:
                    depended_by[dep] = []
                depended_by[dep].append(i)
        
        # First pass: look for hotel/reservation booking sequences to consolidate more aggressively
        consolidated_tasks = []
        skip_indices = set()
        
        # Special handling for booking/reservation tasks - try to combine longer sequences
        booking_related_indices = []
        for i, task in enumerate(tasks):
            task_desc = task['task'].lower()
            if any(term in task_desc for term in ['hotel', 'book', 'reservation', 'room', 'search', 'find', 'fill', 'form', 'select', 'submit']):
                booking_related_indices.append(i)
        
        # Try to find sequences of booking-related tasks
        if len(booking_related_indices) >= 2:
            booking_related_indices.sort()  # Sort by index to maintain order
            
            # Check if they form a dependency chain
            is_chain = True
            for i in range(1, len(booking_related_indices)):
                curr_idx = booking_related_indices[i]
                prev_idx = booking_related_indices[i-1]
                
                # Check if current depends on previous
                if prev_idx not in tasks[curr_idx].get('dependencies', []):
                    is_chain = False
                    break
            
            # If we have a chain, consolidate the whole booking sequence
            if is_chain and len(booking_related_indices) > 1:
                print(f"Found booking sequence with {len(booking_related_indices)} tasks, consolidating...")
                
                # Get the first task in the chain
                first_task_idx = booking_related_indices[0]
                first_task = tasks[first_task_idx]
                
                # Combine all tasks in the chain
                combined_desc = first_task['task']
                for idx in booking_related_indices[1:]:
                    combined_desc += f" and then {tasks[idx]['task']}"
                
                # Create combined task with dependencies of the first task
                combined_task = {
                    "task": combined_desc,
                    "dependencies": first_task.get('dependencies', [])
                }
                
                consolidated_tasks.append(combined_task)
                
                # Mark all tasks in the chain as skipped
                for idx in booking_related_indices:
                    skip_indices.add(idx)
                
                print(f"Consolidated booking sequence into: '{combined_desc}'")
        
        # Second pass: standard consolidation for remaining tasks
        for i, task in enumerate(tasks):
            if i in skip_indices:
                continue
                
            # Check if this task has only one direct dependency
            deps = task.get('dependencies', [])
            
            if len(deps) == 1 and deps[0] not in skip_indices:
                dep_idx = deps[0]
                dep_task = tasks[dep_idx]
                
                # Check if the dependency is only depended on by this task
                if dep_idx in depended_by and len(depended_by[dep_idx]) == 1:
                    # Check for related content using keywords
                    task_desc = task['task'].lower()
                    dep_desc = dep_task['task'].lower()
                    
                    # Keywords that indicate related tasks
                    relation_indicators = [
                        # Task type relationships
                        dep_desc.startswith("search") and any(term in task_desc for term in ["use", "book", "select", "find"]),
                        dep_desc.startswith("find") and any(term in task_desc for term in ["book", "select", "reserve"]),
                        dep_desc.startswith("locate") and any(term in task_desc for term in ["visit", "navigate", "go to"]),
                        "hotel" in dep_desc and any(term in task_desc for term in ["hotel", "room", "book", "reservation"]),
                        "restaurant" in dep_desc and any(term in task_desc for term in ["restaurant", "reservation", "book", "table"]),
                        "research" in dep_desc and any(term in task_desc for term in ["summarize", "write", "report"]),
                        "fill" in task_desc and "form" in task_desc,
                        "submit" in task_desc,
                        "check" in task_desc and "out" in task_desc,
                        
                        # Sequential indicators
                        "and then" in task_desc,
                        "continue" in task_desc,
                        task_desc.startswith("then"),
                        task_desc.startswith("next"),
                        task_desc.startswith("after"),
                        
                        # General web navigation patterns
                        "navigate" in dep_desc and any(term in task_desc for term in ["click", "select", "fill", "input"]),
                        "go to" in dep_desc and any(term in task_desc for term in ["click", "select", "fill", "input"])
                    ]
                    
                    # If any relation indicators match, consolidate
                    if any(relation_indicators):
                        print(f"Consolidating tasks: '{dep_task['task']}' + '{task['task']}'")
                        
                        # Create combined task
                        combined_task = {
                            "task": f"{dep_task['task']} and then {task['task']}",
                            "dependencies": dep_task.get('dependencies', [])
                        }
                        consolidated_tasks.append(combined_task)
                        skip_indices.add(i)
                        skip_indices.add(dep_idx)
                        
                        # Update dependency graph
                        if dep_idx in depended_by:
                            del depended_by[dep_idx]
                        continue
            
            # If not consolidated, keep original task
            if i not in skip_indices:
                consolidated_tasks.append(task)
        
        # Fix dependency indices after consolidation
        index_map = {}
        for old_idx, task in enumerate(tasks):
            if old_idx not in skip_indices:
                new_idx = len([t for t in range(old_idx) if t not in skip_indices])
                index_map[old_idx] = new_idx
        
        # Remap dependencies
        for task in consolidated_tasks:
            new_deps = []
            for dep in task.get('dependencies', []):
                if dep in index_map:
                    new_deps.append(index_map[dep])
            task['dependencies'] = new_deps
        
        print(f"Task consolidation complete. Reduced from {len(tasks)} to {len(consolidated_tasks)} tasks.")
        return consolidated_tasks
=======
            # Clean up worker reference and active websocket
            if self.worker:
                self.worker.websocket = None
            if self._active_websocket == websocket:
                self._active_websocket = None
            print("WebSocket connection closed")

    async def cleanup(self):
        """Clean up resources."""
        if self.pc:
            await self.pc.close()
            self.pc = None
        if self.video_track:
            await self.video_track.stop()
            self.video_track = None
        if self.page:
            await self.page.close()
            self.page = None
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    def run_dashboard(self, host="0.0.0.0", port=8000):
        """Run the web dashboard."""
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)

if __name__ == "__main__":
    nyx = Nyx()
    nyx.run_dashboard()
>>>>>>> single_agent
