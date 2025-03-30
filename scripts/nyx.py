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
    
    Break down complex requests into sequential subtasks that agents can perform. Tasks should be specific and actionable.
    
    IMPORTANT: Consolidate related tasks that can be performed by a single agent. Only create separate agents when:
    1. Tasks require different expertise or capabilities
    2. Tasks must be performed in parallel
    3. Tasks depend on different sources of information
    
    For example, "search for hotels and book a room" should be handled by a single agent, not split across multiple agents.
    
    When creating a plan:
    1. Identify the main steps needed to complete the overall goal
    2. Consolidate related actions into a single task when possible
    3. Only set dependencies between tasks that genuinely need to be performed by different agents
    4. Make each task comprehensive enough to handle logical sequences of actions"""

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