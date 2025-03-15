import os
import sys
import asyncio
from queue import Queue
from playwright.async_api import async_playwright
from worker import Worker
import pygetwindow as gw
import time
import csv
import openai  # Assuming OpenAI API is used for initial input processing
import json
from messages import *
from openai import AsyncOpenAI
import pandas as pd
import traceback

async def async_input(prompt: str, queue: asyncio.Queue):
    """Asynchronously wait for user input and put it in a queue."""
    loop = asyncio.get_event_loop()
    print(f"Prompting for input: {prompt}")
    try:
        user_input = await loop.run_in_executor(None, lambda: input(prompt))
        print(f"Adding to queue for {prompt}: {user_input}")
        await queue.put(user_input)
    except Exception as e:
        print(f"Error getting input: {e}")
        await queue.put("Error getting input")

class Nyx:
    input_list = []

    NYX_PROMPT = """You are an AI orchestrator designed to manage and coordinate multiple agents for complex tasks. You can:
    1. create_csv: Create a CSV file that stores the tasks to be done. Usage: create_csv <filename> <task1> <task2> ...
    2. use_csv: Start autonomous agents on the given CSV. Usage: use_csv <path to csv>
    3. create_agent: Create a new agent for a specific task
    4. destroy_agent: Destroy an agent when its task is complete
    
    Analyze tasks and create/destroy agents as needed based on task complexity and dependencies."""

    def __init__(self):
        """Initialize Nyx with a clean state."""
        # Reset all state variables
        self.input_list = []
        self.MAX_MESSAGES = 100
        self.request_queue = Queue()
        self.workers = []
        self.worker_tasks = {}
        self.input_queues = {}
        self.error_queues = {}  # New: queues for error reporting
        self.results = {}
        self.task_dependencies = {}
        self.available_worker_ids = set()
        
        # Load configuration
        with open("api_config.cfg", 'r') as f:
            cfg = f.read()

        config = {}
        for line in cfg.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('"')
                print(f"{key.strip()}: {value.strip()}")

        if os.environ.get("OPENAI_API_KEY") is not None:
            print(f"Using OpenAI API. Model: {config['openai_model']}")
            self.api = "openai"
            self.MODEL = config["openai_model"]
        elif os.environ.get("XAI_API_KEY") is not None:
            print("Using XAI API")
            self.api = "xai"
            self.MODEL = config["xai_model"]
        else:
            print("Using Ollama.")
            self.api = "ollama"
            self.MODEL = config["ollama_local_model"]

        with open("tools.json", 'r') as f:
            self.tools = json.load(f)["tools"]
        self.config = config

    async def handle_initial_input(self, initial_input):
        """Initialize Nyx components and handle initial input."""
        print("=== Starting handle_initial_input ===")
        # Initialize API client
        api_key = os.environ.get('XAI_API_KEY')
        if self.api == "xai" and not api_key:
            print(f"XAI_API_KEY not set.")
            sys.exit(1)
        if self.api == "openai":
            self.client = AsyncOpenAI()
            print("OpenAI client initialized")
        elif self.api == "xai":
            self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
            print("XAI client initialized")
        elif self.api == "ollama":
            self.client = AsyncOpenAI(api_key="____", base_url='http://localhost:11434/v1')
            print("Ollama client initialized")

        # Initialize browser context if not already done
        if not hasattr(self, 'playwright'):
            print("Initializing Playwright and browser...")
            try:
                self.playwright = await async_playwright().start()
                print("Playwright started")
                
                # Launch browser without persistent context
                print("Launching browser...")
                self.browser = await self.playwright.chromium.launch(
                    headless=False,
                    args=[
                        "--ignore-certificate-errors", 
                        "--disable-extensions",
                        "--disable-blink-features=AutomationControlled",
                    ]
                )
                
                # Create a default context
                print("Creating browser context...")
                self.context = await self.browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
                    viewport=None,
                    permissions=["geolocation"],
                )
                
                # Create initial page
                print("Creating initial page...")
                self.page = await self.context.new_page()
                
                print("Browser initialized successfully")
            except Exception as e:
                print(f"Error initializing browser: {e}")
                traceback.print_exc()
                raise
        
        # If no input provided, we're just initializing
        if not initial_input:
            print("Empty input, just initializing components")
            return
            
        print(f"Processing initial input: {initial_input}")
        
        # Get planning response from API
        planning_prompt = f"""Given the following task, break it down into independent subtasks that can be assigned to different agents.
        Keep the breakdown minimal and focused on the main tasks only.
        
        Task: {initial_input}
        
        Respond with a JSON object in this format:
        {{
            "tasks": [
                {{"task": "Research SpaceX's latest developments, launches, and technology", "dependencies": []}},
                {{"task": "Research RocketLab's latest developments, launches, and technology", "dependencies": []}},
                {{"task": "Research Blue Origin's latest developments, launches, and technology", "dependencies": []}}
            ]
        }}
        
        Guidelines:
        1. Create only the essential research tasks
        2. Focus on the core research objective for each company/topic
        3. Keep task descriptions clear and actionable
        4. Do not include agent creation/management in task descriptions
        5. Each task should be independent and self-contained
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
            )
            print("Received planning response from API")
        except Exception as e:
            print(f"Error getting planning response: {e}")
            traceback.print_exc()
            # If planning fails, treat the input as a single task
            planning_response = type('obj', (object,), {
                'choices': [type('obj', (object,), {
                    'message': type('obj', (object,), {
                        'content': json.dumps({
                            'tasks': [{'task': initial_input, 'dependencies': []}]
                        })
                    })
                })]
            })
            print("Created fallback planning response")
        
        try:
            # Parse the planning response into tasks
            plan = planning_response.choices[0].message.content
            print(f"Task breakdown plan: {plan}")
            
            # Extract tasks from the JSON response
            try:
                # Strip markdown code block syntax if present
                plan_text = plan.strip()
                if plan_text.startswith("```"):
                    plan_text = plan_text.split("\n", 1)[1]  # Remove first line
                if plan_text.endswith("```"):
                    plan_text = plan_text.rsplit("\n", 1)[0]  # Remove last line
                if plan_text.startswith("json"):
                    plan_text = plan_text.split("\n", 1)[1]  # Remove json line
                
                task_plan = json.loads(plan_text)
                tasks = task_plan.get('tasks', [])
                
                # Validate tasks
                filtered_tasks = []
                seen_tasks = set()
                for task in tasks:
                    # Extract research task from combined description
                    task_desc = task['task']
                    if "and research" in task_desc.lower():
                        task_desc = task_desc.split("and research", 1)[1].strip()
                    elif "research" in task_desc.lower():
                        task_desc = task_desc
                    else:
                        continue
                        
                    # Skip duplicate tasks
                    task_lower = task_desc.lower()
                    if task_lower in seen_tasks:
                        continue
                    seen_tasks.add(task_lower)
                    
                    # Create clean task
                    filtered_tasks.append({
                        "task": f"Research {task_desc}",
                        "dependencies": task.get('dependencies', [])
                    })
                
                tasks = filtered_tasks
                print(f"Successfully parsed {len(tasks)} tasks from plan")
            except json.JSONDecodeError:
                print("Error parsing task plan JSON, using single task")
                tasks = [{"task": initial_input, "dependencies": []}]
            
            # Create an agent for each task
            created_workers = []
            for i, task in enumerate(tasks):
                print(f"Creating agent for task {i+1}/{len(tasks)}: {task['task']}")
                worker_id = await self.create_agent(
                    task_description=task["task"],
                    dependencies=task.get("dependencies", [])  # Use get() with default empty list
                )
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
            # Find the next available worker ID
            worker_id = len(self.workers)
            if self.available_worker_ids:
                worker_id = min(self.available_worker_ids)
                self.available_worker_ids.remove(worker_id)

            print(f"Creating agent {worker_id} for task: {task_description}")

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
                if dependencies:
                    self.task_dependencies[worker_id] = dependencies
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
            if 'worker_id' in locals() and worker_id in self.available_worker_ids:
                self.available_worker_ids.remove(worker_id)
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
                while True:
                    deps_completed = all(
                        self.results.get(dep_id, {}).get('status') == 'completed'
                        for dep_id in deps
                    )
                    if deps_completed:
                        print(f"Worker {worker.worker_id} dependencies satisfied")
                        break
                    print(f"Worker {worker.worker_id} waiting for dependencies")
                    await asyncio.sleep(1)
            
            # Main worker loop
            while True:
                print(f"Worker {worker.worker_id} executing step")
                active = await worker.step()
                
                # Store results
                self.results[worker.worker_id] = {
                    'task': worker.current_task,
                    'status': 'active' if active else 'completed',
                    'last_action': worker.messages.messages[-1].content if worker.messages.messages else None
                }
                
                if not active:
                    print(f"Worker {worker.worker_id} has completed its task")
                    break
                    
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            print(f"Worker {worker.worker_id} task was cancelled")
            self.results[worker.worker_id] = {
                'task': worker.current_task,
                'status': 'cancelled',
                'error': 'Task was cancelled'
            }
        except Exception as e:
            print(f"Worker {worker.worker_id} error: {e}")
            traceback.print_exc()
            self.results[worker.worker_id] = {
                'task': worker.current_task,
                'status': 'error',
                'error': str(e)
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
                    try:
                        worker_id = self.request_queue.get_nowait()
                        if worker_id not in self.input_queues or worker_id >= len(self.workers) or not self.workers[worker_id]:
                            print(f"Warning: Worker {worker_id} not found or invalid")
                            self.request_queue.task_done()
                            continue
                            
                        queue = self.input_queues[worker_id]
                        print(f"Input requested by Worker {worker_id}, queue size before prompt: {queue.qsize()}")
                        
                        # Get input from user
                        current_task = self.workers[worker_id].current_task if hasattr(self.workers[worker_id], 'current_task') else "Unknown task"
                        prompt = f"Input for Worker {worker_id} ({current_task}): "
                        
                        # Create a separate queue for this specific input request
                        input_queue = asyncio.Queue()
                        
                        # Create a task to handle the input and set a timeout
                        input_task = asyncio.create_task(async_input(prompt, input_queue))
                        
                        try:
                            # Wait for user input with timeout
                            user_input = await asyncio.wait_for(input_queue.get(), timeout=60)
                            print(f"Providing input for Worker {worker_id}: {user_input}")
                            await queue.put(user_input)
                        except asyncio.TimeoutError:
                            print(f"Timeout waiting for input for Worker {worker_id}")
                            await queue.put("Timeout waiting for input")
                        finally:
                            if not input_task.done():
                                input_task.cancel()
                                
                        self.request_queue.task_done()
                    except Exception as e:
                        print(f"Error handling input request: {e}")
                        traceback.print_exc()
                        try:
                            self.request_queue.task_done()
                        except:
                            pass
            except Exception as e:
                print(f"Fatal error in input request handler: {e}")
                traceback.print_exc()
                await asyncio.sleep(1)  # Prevent tight loop in case of recurring errors

    async def handle_worker_errors(self):
        """Handle error reports from workers."""
        while True:
            for worker_id, error_queue in self.error_queues.items():
                try:
                    while not error_queue.empty():
                        error_data = await error_queue.get()
                        print(f"Error from Worker {worker_id}: {error_data}")
                        
                        # Update results with error state
                        self.results[worker_id] = {
                            'task': error_data['task'],
                            'status': 'error',
                            'error_type': error_data['error_type'],
                            'error_message': error_data['error_message'],
                            'timestamp': error_data['timestamp']
                        }
                        
                        # If it's a fatal error, consider destroying the agent
                        if error_data['error_type'] in ['configuration_error', 'api_error']:
                            print(f"Fatal error in Worker {worker_id}, destroying agent")
                            await self.destroy_agent(worker_id)
                except Exception as e:
                    print(f"Error handling worker errors: {e}")
            await asyncio.sleep(0.1)

    async def start(self):
        """Start the Nyx system."""
        print("Starting Nyx system")
        
        # Start input and error handlers
        input_task = asyncio.create_task(self.handle_input_requests())
        error_task = asyncio.create_task(self.handle_worker_errors())
        print("Input and error handler tasks created")

        # Wait for all worker tasks to complete
        try:
            if self.worker_tasks:
                print(f"Waiting for {len(self.worker_tasks)} worker tasks to complete")
                # Use asyncio.gather instead of wait to ensure all tasks complete
                await asyncio.gather(*self.worker_tasks.values(), return_exceptions=True)
                print("All worker tasks have completed")
            else:
                print("No worker tasks to wait for")
                # If no worker tasks, just wait a bit to keep the system running
                await asyncio.sleep(10)
                
            # Cancel input and error handlers after workers are done
            print("Cancelling input and error handler tasks")
            input_task.cancel()
            error_task.cancel()
            
        except asyncio.CancelledError:
            print("Nyx shutting down due to cancellation...")
            for task in self.worker_tasks.values():
                if not task.done():
                    task.cancel()
            input_task.cancel()
            error_task.cancel()
        except Exception as e:
            print(f"Error in Nyx start: {e}")
            traceback.print_exc()
        finally:
            print("Nyx execution completed, cleaning up resources")
            # Don't close browser here - let the dashboard handle it
            # This prevents premature browser closure
            # if hasattr(self, 'browser'):
            #     await self.browser.close()
            # if hasattr(self, 'playwright'):
            #     await self.playwright.stop()
            # print("Browser and Playwright stopped")
            
        print("Nyx system execution completed")