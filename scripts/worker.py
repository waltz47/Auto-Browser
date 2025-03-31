import os
import time
import json
import asyncio
from playwright.async_api import Page
from openai import AsyncOpenAI
from typing import Dict, Any, Union
from pathlib import Path
import traceback

# Import web tools and messages
from web.web import get_page_elements, get_main_content
from web.handler import process, test_selectors_on_page, enhance_json_with_selectors
from tools import functions as web_tools
from messages import MessageHistory, Message
from orchestrator import Orchestrator

class Worker:
    def __init__(self, page: Page, worker_id: int, request_queue, api: str, model: str, max_messages: int, tools=None, websocket=None, enable_vision=False):
        """Initialize a worker with a browser page and configuration."""
        self.page = page
        self.worker_id = worker_id
        self.api = api
        self.model = model
        self.max_messages = max_messages
        self.element_cache: Dict[str, str] = {}
        self.client = None
        self.is_running = True
        self.waiting_for_input = False
        self.current_task = "Initializing"
        self.tools = tools or web_tools
        self.messages = self._init_message_history()
        self.websocket = websocket
        self.enable_vision = enable_vision
        self.first_step_over = False
        
        # Initialize orchestrator
        self.orchestrator = Orchestrator(model=model)
        self.current_workflow = None

    def _init_message_history(self) -> MessageHistory:
        """Initialize the message history with system prompt."""
        try:
            with open("scripts/custom.log", "r") as f:
                custom_instructions = f.read()
        except FileNotFoundError:
            custom_instructions = ""
            print("No custom instructions found")

        tools_description = """
IMPORTANT: You have access to the following tools to help complete your tasks. Each tool call is an atomic operation that may succeed or fail:

1. move_to_url(url: str) - Navigate to a specific URL
2. get_url_contents() - Get the contents of the current page
3. send_keys_to_element(xpathSelector: str, keys: str) - Send text to an element
4. call_submit(xpathSelector: str) - Submit a form
5. click_element(xpathSelector: str) - Click on an element
6. highlight_element(xpathSelector: str) - Highlight an element for visibility
7. move_and_click_at_page_position(x: float, y: float) - Click at specific coordinates

Additionally, you have special tools to manage task status:
- mark_task_complete(task_id: str, result: str) - Mark a task as successfully completed
- mark_task_failed(task_id: str, reason: str) - Mark a task as failed after exhausting all options
- display_message(message: str) - Show a message to the user

Remember:
- Individual tool calls may fail (e.g., element not found) - this is normal and you should try alternatives
- A task fails only when you've exhausted all possible approaches
- Only mark a task complete when you've achieved its objective
- You can make multiple tool calls within a single task
"""

        system_prompt = f'''You are an advanced AI agent capable of performing complex web-based tasks. Your capabilities include:

### Task Management
- Break down complex tasks into manageable steps
- Try multiple approaches if initial attempts fail
- Only mark tasks as complete when objectives are achieved
- Only mark tasks as failed after exhausting all options
- Maintain task state across multiple tool calls

### Information Processing
- Research and data gathering through web searches
- Information verification from multiple sources
- Analysis and synthesis of complex data
- Fact-checking and validation
- Structured and unstructured data processing

### Problem Solving
- Systematic breakdown of complex tasks
- Step-by-step solution implementation
- Error troubleshooting and resolution
- Adaptive problem-solving approaches
- Dynamic response to changing requirements

Instructions:
1. Each task is a goal to achieve, which may require multiple tool calls
2. Tool calls are atomic operations that may succeed or fail
3. Failed tool calls don't mean task failure - try alternative approaches
4. Only mark a task as failed when you've exhausted all possible approaches
5. Only mark a task as complete when you've achieved its objective
6. Handle errors and blocked states by trying alternative approaches
7. Only request user input if absolutely necessary

{tools_description}

{custom_instructions}'''

        return MessageHistory(system_prompt)

    async def setup_client(self):
        """Set up the OpenAI client based on API configuration."""
        try:
            if self.client is not None:
                return
                
            if self.api == "openai":
                self.client = AsyncOpenAI()
            elif self.api == "xai":
                api_key = os.environ.get('XAI_API_KEY')
                if not api_key:
                    raise ValueError("XAI_API_KEY not set")
                self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
            elif self.api == "ollama":
                self.client = AsyncOpenAI(api_key="____", base_url='http://localhost:11434/v1')
            else:
                raise ValueError(f"Unsupported API type: {self.api}")
                
            print("API client initialized successfully")
        except Exception as e:
            print(f"Failed to initialize API client: {str(e)}")
            raise

    async def process_user_input(self, user_input: str):
        """Process user input by creating a workflow and starting execution."""
        try:
            # Create workflow using orchestrator
            self.current_workflow = await self.orchestrator.create_workflow(user_input)
            
            # Send initial workflow info to user
            workflow_msg = f"\nAuto Browser: Created workflow: {self.current_workflow.title}\n"
            for i, point in enumerate(self.current_workflow.points, 1):
                workflow_msg += f"\n{i}. {point.title}\n"
                workflow_msg += f"   Description: {point.description}\n"
            
            await self.send_to_websocket(workflow_msg)
            
            # Start executing workflow
            return True
            
        except Exception as e:
            error_msg = f"Error processing user input: {str(e)}"
            await self.send_to_websocket(error_msg)
            return False

    async def step(self) -> bool:
        """Execute the next step in the workflow."""
        if not self.current_workflow:
            return False

        try:
            # Get current task details
            current_task = self.orchestrator.get_current_task()
            
            # Only stop if there are no more tasks AND we're at the end of all points
            if not current_task:
                if self.current_workflow.current_point_index >= len(self.current_workflow.points):
                    await self.send_to_websocket("\nAuto Browser: Workflow completed! Let me know if you need anything else.")
                    return False
                else:
                    # We still have more points to process
                    print("[Worker] Moving to next point's tasks")
                    return True

            # Update progress
            await self.send_progress_update(current_task["progress"])

            # Print current task info
            print(f"[Worker] Executing task: {current_task['task']}")
            print(f"[Worker] Point: {current_task['progress']['current_point_title']}")
            print(f"[Worker] Task index: {current_task['progress']['current_task']}/{current_task['progress']['total_tasks']}")

            # Execute the task
            active = await self._execute_step(current_task)
            print(f"[Worker] Task execution result - active: {active}")

            # Always return True unless explicitly waiting for input or workflow complete
            # This ensures we continue processing tasks across points
            return True

        except Exception as e:
            error_details = traceback.format_exc()
            print(f"[Worker Error] Caught exception in step: {e}\nDetails: {error_details}")
            await self.send_to_websocket(f"Error in step: {e}", debug=True)
            
            # Ask orchestrator for help
            context = {
                "current_point": self.current_workflow.points[self.current_workflow.current_point_index].title,
                "current_task": current_task["task"] if current_task else "Unknown",
                "error_message": str(e),
                "traceback": error_details
            }
            print(f"[Worker Error] Asking orchestrator for help with context: {context}")
            
            help_response = await self.orchestrator.handle_worker_request(
                f"Error occurred: {str(e)}. Need guidance on how to proceed.",
                context
            )
            print(f"[Worker Error] Received help response from orchestrator: '{help_response}'")
            
            if help_response.startswith("USER_INPUT_REQUIRED:"):
                print("[Worker Error] Orchestrator requested user input.")
                user_prompt = help_response[len("USER_INPUT_REQUIRED:"):].strip()
                await self.send_to_websocket(f"\nAuto Browser: {user_prompt}")
                print(f"[Worker Error] Sent prompt to user: '{user_prompt}'")
                self.waiting_for_input = True
                print("[Worker Error] Set waiting_for_input = True")
                return False
            else:
                print("[Worker Error] Orchestrator provided guidance. Adding to messages and retrying.")
                self.messages.add_assistant_text(help_response)
                return True

    async def send_progress_update(self, progress: Dict[str, Any]):
        """Send progress update to the dashboard."""
        if self.websocket:
            try:
                progress_msg = {
                    "type": "progress_update",
                    "data": progress
                }
                await self.websocket.send_text(json.dumps(progress_msg))
            except Exception as e:
                print(f"Error sending progress update: {e}")

    async def move_to_url(self, url: str) -> str:
        """Navigate to a URL with retry logic and error handling."""
        max_retries = 3
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                # Try different navigation options based on retry count
                if retry_count == 0:
                    # First attempt: Standard navigation with longer timeout
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                elif retry_count == 1:
                    # Second attempt: Force HTTP1.1 and clear cache/cookies
                    await self.page.context.clear_cookies()
                    await self.page.route("**/*", lambda route: route.continue_(
                        headers={"Accept": "*/*", "Upgrade-Insecure-Requests": "1", "Connection": "keep-alive"}
                    ))
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                else:
                    # Final attempt: Network conditions and different wait strategy
                    await self.page.context.clear_cookies()
                    await self.page.set_extra_http_headers({"Accept-Encoding": "gzip, deflate"})
                    await self.page.goto(url, wait_until="load", timeout=60000)

                # Wait for network to be idle and add small delay
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass  # Don't fail if networkidle times out
                
                await asyncio.sleep(2)
                print(f"Successfully navigated to: {url} (attempt {retry_count + 1})")
                self.element_cache.clear()
                return f"Navigated to {url}. Contents: {await self.get_url_contents()}"

            except Exception as e:
                last_error = str(e)
                retry_count += 1
                if retry_count < max_retries:
                    # Exponential backoff
                    wait_time = 2 ** retry_count
                    print(f"Navigation attempt {retry_count} failed. Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    # Clear any error states
                    try:
                        await self.page.reload()
                    except:
                        pass

        # If all retries failed, return detailed error
        error_msg = f"Failed to navigate to URL after {max_retries} attempts. Last error: {last_error}"
        print(error_msg)
        return f"Error navigating to URL: {error_msg}"

    async def get_url_contents(self) -> str:
        """Retrieve and cache the current page's contents."""
        cache_key = self.page.url
        if cache_key in self.element_cache:
            return self.element_cache[cache_key]
        
        try:
            await asyncio.sleep(4)
            await self.page.wait_for_load_state(state="domcontentloaded")
            content = await self.page.content()
            
            elements = await get_page_elements(self.page)
            elements_info = await process(self, elements)
            main_content = await get_main_content(self.page)
            data = f"***PAGE JSON***\n\n{elements_info}\n\n{main_content}\n\n ***END OF PAGE JSON***"
            
            self.element_cache[cache_key] = data
            return data
        except Exception as e:
            print(f"Error getting page contents: {e}")
            return "Error retrieving page contents"

    async def send_keys_to_element(self, xpathSelector: str, keys: str) -> str:
        """Send keys to an element identified by xpath."""
        locator, error = await self._get_locator(xpathSelector)
        if error:
            return error
        try:
            await locator.click(force=True)
            await locator.fill("")
            await self.highlight_element(xpathSelector)
            await locator.type(keys, delay=10)
            await asyncio.sleep(2)
            return f"Keys sent. Contents: {await self.get_url_contents()}"
        except Exception as e:
            return f"Error sending keys: {str(e)}"

    async def call_submit(self, xpathSelector: str) -> str:
        """Submit a form using the element at xpath."""
        locator, error = await self._get_locator(xpathSelector)
        if error:
            return error
        try:
            form = await locator.evaluate("el => el.closest('form')")
            if form:
                await locator.evaluate("el => el.form.submit()")
            else:
                await locator.press('Enter')
            return "Form submitted"
        except Exception as e:
            return f"Error submitting form: {str(e)}"

    async def click_element(self, xpathSelector: str) -> str:
        """Click an element identified by xpath."""
        locator, error = await self._get_locator(xpathSelector)
        if error:
            return error
        try:
            await locator.scroll_into_view_if_needed(timeout=2000)
            await self.highlight_element(xpathSelector)
            await locator.click(force=True)
            await asyncio.sleep(3)
            return f"Element clicked. Contents: {await self.get_url_contents()}"
        except Exception as e:
            return f"Error clicking element: {str(e)}"

    async def highlight_element(self, xpathSelector: str, color='red', duration=5000) -> str:
        """Highlight an element for visual debugging."""
        locator, error = await self._get_locator(xpathSelector)
        if error:
            return error
        try:
            bounding_box = await locator.bounding_box()
            if bounding_box:
                box_data = {'box': bounding_box, 'color': color, 'duration': duration}
                await self.page.evaluate(
                    '''(data) => {
                        const div = document.createElement('div');
                        div.style.cssText = `position:absolute;z-index:9999;border:4px solid ${data.color};pointer-events:none;`;
                        div.style.left = `${data.box.x + window.scrollX}px`;
                        div.style.top = `${data.box.y + window.scrollY}px`;
                        div.style.width = `${data.box.width}px`;
                        div.style.height = `${data.box.height}px`;
                        document.body.appendChild(div);
                        setTimeout(() => div.parentNode?.removeChild(div), data.duration);
                    }''', box_data)
            return "Element highlighted"
        except Exception as e:
            print(f"Error highlighting: {e}")
            return "Error highlighting element"

    async def move_and_click_at_page_position(self, x=None, y=None, location_x=None, location_y=None) -> str:
        """Move to and click at specific page coordinates."""
        try:
            x_coord = x if x is not None else location_x
            y_coord = y if y is not None else location_y
            
            if x_coord is None or y_coord is None:
                return "Error - Missing coordinates for clicking"
                
            await self.page.mouse.move(x_coord, y_coord)
            await self.page.mouse.click(x_coord, y_coord)
            return f"Clicked at ({x_coord}, {y_coord})"
        except Exception as e:
            return f"Error clicking at position: {str(e)}"

    async def _get_locator(self, xpathSelector: str, first_only=False) -> tuple[Any, str]:
        """Retrieve a locator for an xpath, handling multiple matches."""
        selector = f"xpath={xpathSelector}"
        try:
            locator = self.page.locator(selector)
            count = await locator.count()
            if (count == 0):
                return None, "Invalid XPath: No elements found"
            if (count > 1 and not first_only):
                return None, f"There are multiple HTML elements found for the xpath selector: {selector}. Pick the required one with [] selector notation. Eg: xpath=//div[@class='class-name'][n]"
            if first_only:
                locator = locator.first
            return locator, None
        except Exception as e:
            return None, f"Error getting locator: {str(e)}"

    async def send_to_websocket(self, message: str, debug: bool = False):
        """Send a message to the websocket if available."""
        if debug:
            # Debug messages go to terminal only
            print(message)
        elif self.websocket:
            # Regular messages go to dashboard
            print(f"[Worker] Attempting to send to websocket {id(self.websocket)}: {message[:50].strip()}...") # Log attempt
            try:
                await self.websocket.send_text(message.strip())
                print(f"[Worker] Sent message successfully to {id(self.websocket)}.") # Log success
            except Exception as e:
                print(f"[Worker] Error sending to websocket {id(self.websocket)}: {e}") # Log error
        else:
            # If no websocket, everything goes to terminal
            print(f"[Worker] No websocket available. Printing to terminal: {message}")

    async def get_current_task(self) -> str:
        """Get information about the current task."""
        if not self.current_workflow:
            return json.dumps({"error": "No workflow active"})
            
        point_index = self.current_workflow.current_point_index
        point = self.current_workflow.points[point_index]
        task_index = point.current_task_index
        task = point.tasks[task_index]
        
        return json.dumps({
            "task_id": f"{point_index}.{task_index}",
            "point_title": point.title,
            "task_description": task,
            "total_points": len(self.current_workflow.points),
            "total_tasks": len(point.tasks)
        })

    async def mark_task_complete(self, task_id: str, result: str) -> str:
        """Mark a task as completed successfully."""
        try:
            point_index, task_index = map(int, task_id.split("."))
            
            # Verify this is the current task
            if (self.current_workflow.current_point_index != point_index or 
                self.current_workflow.points[point_index].current_task_index != task_index):
                return "Error: Cannot complete a task that is not current"
            
            # Update progress
            self.orchestrator.update_progress(point_index, task_index, completed=True)
            
            # Send success message
            await self.send_to_websocket(f"\nAuto Browser: ✓ {result}")
            
            # Handle progression to next task/point
            current_point = self.current_workflow.points[point_index]
            print(f"[Worker] Current point index: {point_index}, task index: {task_index}")
            print(f"[Worker] Total tasks in point: {len(current_point.tasks)}")
            
            # If we completed all tasks in current point
            if task_index >= len(current_point.tasks) - 1:
                print("[Worker] Completed all tasks in current point")
                # If we have more points, move to first task of next point
                if point_index < len(self.current_workflow.points) - 1:
                    print(f"[Worker] Moving to next point {point_index + 1}")
                    self.orchestrator.update_progress(point_index + 1, 0)
                else:
                    print("[Worker] No more points, workflow complete")
                    await self.send_to_websocket("\nAuto Browser: Workflow completed! Let me know if you need anything else.")
            else:
                print(f"[Worker] Moving to next task {task_index + 1}")
                # Move to next task in current point
                self.orchestrator.update_progress(point_index, task_index + 1)
            
            return "Task marked as complete"
            
        except Exception as e:
            return f"Error marking task complete: {str(e)}"

    async def mark_task_failed(self, task_id: str, reason: str) -> str:
        """Mark a task as failed."""
        try:
            point_index, task_index = map(int, task_id.split("."))
            
            # Verify this is the current task
            if (self.current_workflow.current_point_index != point_index or 
                self.current_workflow.points[point_index].current_task_index != task_index):
                return "Error: Cannot fail a task that is not current"
            
            # Send failure message
            await self.send_to_websocket(f"\nAuto Browser: ❌ Task failed: {reason}")
            
            # Ask orchestrator for guidance
            context = {
                "point_title": self.current_workflow.points[point_index].title,
                "task": self.current_workflow.points[point_index].tasks[task_index],
                "failure_reason": reason
            }
            
            help_response = await self.orchestrator.handle_worker_request(
                f"Task failed: {reason}. Need guidance on how to proceed.",
                context
            )
            
            if help_response.startswith("USER_INPUT_REQUIRED:"):
                user_prompt = help_response[len("USER_INPUT_REQUIRED:"):].strip()
                await self.send_to_websocket(f"\nAuto Browser: {user_prompt}")
                self.waiting_for_input = True
            else:
                self.messages.add_assistant_text(help_response)
            
            return "Task marked as failed"
            
        except Exception as e:
            return f"Error marking task failed: {str(e)}"

    async def display_message(self, message: str) -> str:
        """Display a message to the user in the chat."""
        try:
            await self.send_to_websocket(f"\nAuto Browser: {message}")
            return "Message displayed successfully"
        except Exception as e:
            return f"Error displaying message: {str(e)}"

    async def _execute_step(self, current_task: Dict[str, Any]) -> bool:
        """Execute a single step using the existing message processing logic."""
        try:
            # Get current task info
            task_info = json.loads(await self.get_current_task())
            if "error" in task_info:
                return False

            # Add current task to messages
            self.messages.add_system_text(f"""Current workflow point: {task_info['point_title']}
Current task: {task_info['task_description']}
Task ID: {task_info['task_id']}
Execute this task using the available tools. Mark the task as complete or failed based on the outcome.""")

            # Get response from API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self.messages.get_messages_for_api(),
                tools=self.tools,
                tool_choice="auto",
                temperature=0.7,
                stream=False
            )

            # Extract content and tool calls
            content = response.choices[0].message.content or ""
            tool_calls = response.choices[0].message.tool_calls or []

            # Process tool calls if any
            if tool_calls:
                # First collect all tool responses
                tool_responses = []  # Store all tool responses
                task_status_changed = False  # Track if task was marked complete/failed
                
                print("\n=== Tool Calls Debug ===")
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    # Print tool call details
                    print(f"\n[Tool Call] {function_name}")
                    print(f"Arguments: {json.dumps(arguments, indent=2)}")

                    if hasattr(self, function_name):
                        try:
                            tool_function = getattr(self, function_name)
                            result = await tool_function(**arguments)
                            tool_responses.append((tool_call.id, result, function_name))
                            
                            # Print result
                            print(f"Result: {result}")
                            
                            # Check if this was a task status change
                            if function_name in ["mark_task_complete", "mark_task_failed"] and "Error" not in result:
                                task_status_changed = True
                                print(f"[Worker] Task status changed via {function_name}")
                            elif "Error" in result:
                                print(f"[Error] Tool call failed: {result}")
                        except Exception as e:
                            error_result = f"Error executing {function_name}: {str(e)}"
                            tool_responses.append((tool_call.id, error_result, function_name))
                            print(f"[Exception] {error_result}")
                    else:
                        error_result = f"Error: Function {function_name} is not available"
                        tool_responses.append((tool_call.id, error_result, "error"))
                        print(f"[Error] {error_result}")
                
                print("\n=== End Tool Calls Debug ===\n")

                # Now add the assistant message with tool calls
                message = Message(
                    role="assistant",
                    content=content,
                    tool_calls=[{
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in tool_calls]
                )
                self.messages.add_message(message)

                # Then add all tool responses to message history
                for tool_call_id, result, function_name in tool_responses:
                    self.messages.add_tool_response(tool_call_id, result, function_name)

                # Only stop if task status was explicitly changed
                return not task_status_changed

            # If there are no tool calls but we have content, display it
            if content.strip():
                await self.display_message(content.strip())
                await self.mark_task_complete(task_info['task_id'], content.strip())
                return False

            # If no tool calls and no content, let the assistant continue
            return True

        except Exception as e:
            # Handle unexpected errors
            print(f"[Worker] Error in _execute_step: {str(e)}")
            if task_info and 'task_id' in task_info:
                await self.mark_task_failed(task_info['task_id'], f"Unexpected error: {str(e)}")
            return True

    async def initialize(self):
        """Initialize the worker and send ready message."""
        await self.setup_client()