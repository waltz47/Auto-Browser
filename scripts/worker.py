import os
import time
import json
import asyncio
from playwright.async_api import Page
from openai import AsyncOpenAI
from typing import Dict, Any, Union
from pathlib import Path
import traceback
import base64

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

### Task Completion Detection
CRITICAL: Before executing any actions for the current task:
1. Review the conversation history thoroughly
2. Check if the current task's objective has already been achieved in previous steps
3. If you find evidence that the current task's goal was already met:
   - Call mark_task_complete immediately with the current task_id
   - Include a brief explanation referencing when/how it was previously completed
4. Only proceed with new actions if you're certain the task hasn't been completed yet
5. When in doubt about completion, check the actual state rather than assuming

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
            for i, task in enumerate(self.current_workflow.tasks, 1):
                workflow_msg += f"\n{i}. {task.title}\n"
                workflow_msg += f"   Description: {task.description}\n"
            
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
            
            # Stop if there are no more tasks
            if not current_task:
                await self.send_to_websocket("\nAuto Browser: Workflow completed! Let me know if you need anything else.")
                return False

            # Update progress - ensure we handle websocket errors gracefully
            try:
                await self.send_progress_update(current_task["progress"])
            except Exception as e:
                print(f"Error sending progress update: {e}")
                # Continue execution even if progress update fails

            # Print current task info
            print(f"[Worker] Executing task: {current_task['task']}")
            print(f"[Worker] Task: {current_task['task_title']}")
            print(f"[Worker] Task index: {current_task['progress']['current_task']}/{current_task['progress']['total_tasks']}")

            # Execute the task
            active = await self._execute_step(current_task)
            print(f"[Worker] Task execution result - active: {active}")

            return True

        except Exception as e:
            error_details = traceback.format_exc()
            print(f"[Worker Error] Caught exception in step: {e}\nDetails: {error_details}")
            
            # Try to send error message, but don't fail if websocket is closed
            try:
                await self.send_to_websocket(f"Error in step: {e}", debug=True)
            except Exception as ws_error:
                print(f"Could not send error to websocket: {ws_error}")
            
            # Ask orchestrator for help
            try:
                context = {
                    "current_task": str(current_task["task"]) if current_task else "Unknown",
                    "error_message": str(e),
                    "traceback": error_details
                }
                
                help_response = await self.orchestrator.handle_worker_request(
                    f"Error occurred: {str(e)}. Need guidance on how to proceed.",
                    context
                )
                
                if help_response.startswith("USER_INPUT_REQUIRED:"):
                    user_prompt = help_response[len("USER_INPUT_REQUIRED:"):].strip()
                    try:
                        await self.send_to_websocket(f"\nAuto Browser: {user_prompt}")
                    except Exception:
                        print(f"Could not send prompt to websocket: {user_prompt}")
                    self.waiting_for_input = True
                    return False
                else:
                    self.messages.add_assistant_text(help_response)
                    return True
                    
            except Exception as help_error:
                print(f"Error getting help from orchestrator: {help_error}")
                return False  # Stop processing on critical error

    async def send_progress_update(self, progress: Dict[str, Any]):
        """Send progress update to the dashboard."""
        if self.websocket:
            try:
                # Create a copy of the progress dict to avoid modifying the original
                display_progress = progress.copy()
                
                # Convert to one-based task index for display only
                display_progress['current_task'] = int(progress.get('current_task', 0)) + 1
                
                # Keep the original progress percentage which is based on completed tasks
                display_progress['overall_progress'] = int(progress.get('overall_progress', 0))
                
                progress_msg = {
                    "type": "progress_update",
                    "data": display_progress
                }
                await self.websocket.send_text(json.dumps(progress_msg))
            except Exception as e:
                print(f"Error sending progress update: {e}")

    async def move_to_url(self, url: str) -> str:
        """Navigate to a URL with retry logic and error handling."""
        max_retries = 3
        retry_count = 0
        last_error = None
        self.first_step_over = True

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
                
                # Get new page contents
                contents = await self.get_url_contents()
                self.element_cache[self.page.url] = contents
                return f"Navigated to {url}. Contents: {contents}"

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
         # Clean up message history before navigating to new URL
        self.messages.trim_history(self.max_messages)
        self.element_cache.clear()
        
        if cache_key in self.element_cache:
            return self.element_cache[cache_key]
        
        try:
            # Wait for page to be ready
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            await asyncio.sleep(2)  # Give time for dynamic content
            
            try:
                # Try to wait for network to be idle, but don't fail if it times out
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception as e:
                print(f"Warning: Network not idle, continuing anyway: {e}")
            
            try:
                # Get page elements and process them into JSON
                elements = await get_page_elements(self.page)
                elements_info = await process(self, elements)
                
                # Cache and return only the JSON data
                self.element_cache[cache_key] = elements_info
                return elements_info
                
            except Exception as e:
                print(f"Warning: Could not get page elements: {e}")
                return json.dumps({
                    "error": "Could not extract page elements",
                    "details": str(e)
                })
            
        except Exception as e:
            error_msg = f"Error getting page contents: {str(e)}"
            print(error_msg)
            return json.dumps({
                "error": "Error retrieving page contents",
                "details": str(e)
            })

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
            # Wait for element to be present and visible
            await self.page.wait_for_selector(f"xpath={xpathSelector}", 
                state="visible", 
                timeout=10000
            )
            
            # Ensure page is loaded
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)  # Give dynamic content time to load
            
            # Try to scroll element into view
            try:
                await locator.scroll_into_view_if_needed(timeout=5000)
            except Exception as e:
                print(f"Warning: Could not scroll to element: {e}")
            
            # Highlight the element we're trying to click
            await self.highlight_element(xpathSelector)
            
            # Click with force if needed
            await locator.click(force=True, timeout=5000)
            await asyncio.sleep(3)  # Wait for any navigation/changes
            
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
                # Get text content and attributes for each matching element
                elements_info = []
                for i in range(count):
                    try:
                        element = locator.nth(i)
                        text = await element.text_content() or ""
                        text = text.strip()[:50] + "..." if len(text.strip()) > 50 else text.strip()
                        class_attr = await element.get_attribute("class") or ""
                        id_attr = await element.get_attribute("id") or ""
                        elements_info.append(f"[{i+1}] Text: '{text}', class='{class_attr}', id='{id_attr}'")
                    except:
                        elements_info.append(f"[{i+1}] <element details unavailable>")
                
                elements_str = "\n".join(elements_info)
                return None, f"Multiple elements ({count}) found for selector: {selector}\nAvailable elements:\n{elements_str}\nPick the required one with [] selector notation. Example: {xpathSelector}[n]"
            
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
        try:
            if not self.current_workflow:
                return json.dumps({"error": "No workflow active"})
            
            # Get current task from orchestrator
            orchestrator_task = self.orchestrator.get_current_task()
            if not orchestrator_task:
                return json.dumps({"error": "No current task available"})
            
            # Get current task details
            task_index = self.current_workflow.current_task_index
            total_tasks = len(self.current_workflow.tasks)
            
            # Create task info using orchestrator's plan - convert to one-based indexing
            task_info = {
                "task_id": str(task_index + 1),  # Convert to one-based
                "task_title": orchestrator_task["task_title"],
                "task_description": str(orchestrator_task["task"]),
                "total_tasks": total_tasks,
                "current_task": task_index + 1,  # Convert to one-based
                "progress": {
                    "current_task": task_index,  # Keep zero-based for internal use
                    "total_tasks": total_tasks,
                    "current_task_title": orchestrator_task["task_title"],
                    "current_task_description": str(orchestrator_task["task"])
                }
            }
            
            return json.dumps(task_info)
            
        except Exception as e:
            error_msg = f"[Worker] Error in get_current_task: {str(e)}"
            print(error_msg)
            return json.dumps({
                "error": "Failed to get current task",
                "details": str(e)
            })

    async def _execute_step(self, current_task: Dict[str, Any]) -> bool:
        """Execute a single step using the existing message processing logic."""
        task_info = None
        try:
            # Get current task info
            task_info = json.loads(await self.get_current_task())
            if "error" in task_info:
                error_msg = f"Cannot proceed: {task_info['error']}"
                if 'details' in task_info:
                    error_msg += f" ({task_info['details']})"
                await self.display_message(error_msg)
                return False

            # Add current task to messages
            self.messages.add_system_text(f"""Current task: {task_info['task_description']}
Task ID: {task_info['task_id']}
Execute this task using the available tools. Only mark the task as complete when you have fully achieved its objective, or mark it as failed if you've exhausted all possible approaches.""")

            # Log messages to chat.log
            await self._log_messages()
            print("Messages logged")

            # Add vision support if enabled
            if self.enable_vision and self.first_step_over:
                print("Taking screenshot")
                # Take screenshot of current page
                screenshot = await self.page.screenshot(type='jpeg', quality=80)
                if screenshot:
                    # Save screenshot to temporary file
                    temp_path = Path("temp_screenshot.jpg")
                    temp_path.write_bytes(screenshot)
                    
                    # Find last user message or create new one
                    last_message = None
                    for msg in reversed(self.messages.messages):
                        if msg.role == "user":
                            last_message = msg
                            break
                    
                    if last_message:
                        # Convert existing content to list format if it's a string
                        if isinstance(last_message.content, str):
                            text_content = last_message.content
                            last_message.content = []
                            if text_content.strip():  # Only add text if not empty
                                last_message.content.append({
                                    "type": "text",
                                    "text": text_content
                                })
                    else:
                        # Create new user message if no existing user message found
                        last_message = Message(role="user", content=[])
                        self.messages.add_message(last_message)
                    
                    # Add image to the message content
                    with open(temp_path, "rb") as image_file:
                        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                        last_message.content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}",
                                "detail": "high"
                            }
                        })
                    
                    # Clean up temp file
                    temp_path.unlink()

            print("Getting response from API")
            # Get response from API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self.messages.get_messages_for_api(),
                tools=self.tools,
                tool_choice="auto",
                temperature=0.3,
                stream=False
            )
            print(f"Response: {response}")
            
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
                            print(f"Result: {str(result)[:500]}")
                            
                            # Check if this was a task status change
                            if function_name in ["mark_task_complete", "mark_task_failed"] and "Error" not in result:
                                task_status_changed = True
                                print(f"[Worker] Task status changed via {function_name}")
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

                # Continue processing unless task was explicitly marked complete/failed
                return not task_status_changed

            # If there are no tool calls but we have content, display it
            if content.strip():
                await self.display_message(content.strip())
                return True  # Continue processing since no task status change

            # If no tool calls and no content, let the assistant continue
            return True

        except Exception as e:
            # Handle unexpected errors
            error_msg = f"[Worker] Error in _execute_step: {str(e)}"
            print(error_msg)
            
            # Only try to mark task as failed if we have valid task info
            if task_info and isinstance(task_info, dict) and 'task_id' in task_info:
                await self.mark_task_failed(task_info['task_id'], f"Unexpected error: {str(e)}")
            else:
                await self.display_message(f"Error: {str(e)}")
            return False  # Stop processing on error

    async def _log_messages(self) -> None:
        """Log all messages to chat.log file."""
        try:
            # Create log directory if it doesn't exist
            os.makedirs("log", exist_ok=True)
            
            # Write messages to chat.log
            with open("log/chat.log", "w", encoding="utf-8") as f:
                f.write("=== Chat History ===\n\n")
                for msg in self.messages.messages:
                    # Write role
                    f.write(f"[{msg.role.upper()}]\n")
                    
                    # Handle different content types
                    if isinstance(msg.content, str):
                        f.write(f"{msg.content}\n")
                    elif isinstance(msg.content, list):
                        for item in msg.content:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    f.write(f"{item['text']}\n")
                                elif item.get("type") == "image_url":
                                    f.write("[IMAGE ATTACHMENT]\n")
                    
                    # Write tool calls if present
                    if msg.tool_calls:
                        f.write("\nTool Calls:\n")
                        for tool_call in msg.tool_calls:
                            f.write(f"- {tool_call['function']['name']}\n")
                            f.write(f"  Arguments: {tool_call['function']['arguments']}\n")
                    
                    f.write("\n---\n\n")
                
                f.write("=== End Chat History ===\n")
            
            print(f"[Worker] Messages logged to log/chat.log")
            
        except Exception as e:
            print(f"[Worker] Error logging messages: {e}")

    async def mark_task_complete(self, task_id: str, result: str) -> str:
        """Mark a task as completed successfully."""
        try:
            # Parse task ID (convert from one-based to zero-based)
            task_index = int(task_id) - 1
            
            # Send success message
            await self.send_to_websocket(f"\nAuto Browser: ✓ {result}")
            
            # Update progress in orchestrator
            self.orchestrator.update_progress(task_index, completed=True)
            
            # Check if we have more tasks
            if task_index < len(self.current_workflow.tasks) - 1:
                # Move to next task
                print(f"[Worker] Moving to next task: {self.current_workflow.tasks[task_index + 1].title}")
                print(f"[Worker] Task {task_index + 2}/{len(self.current_workflow.tasks)}")  # Display in one-based
            else:
                # Workflow is complete
                await self.send_to_websocket("\nAuto Browser: Workflow completed! Let me know if you need anything else.")
            
            return "Task marked as complete"
            
        except Exception as e:
            error_msg = f"Error marking task complete: {str(e)}"
            print(f"[Worker] {error_msg}")
            return error_msg

    async def mark_task_failed(self, task_id: str, reason: str) -> str:
        """Mark a task as failed but continue with the workflow."""
        try:
            # Parse task ID (convert from one-based to zero-based)
            task_index = int(task_id) - 1
            
            # Send failure message
            await self.send_to_websocket(f"\nAuto Browser: ❌ Task {task_id} failed: {reason}")  # Keep one-based in message
            
            # Move to next task if available
            if task_index < len(self.current_workflow.tasks) - 1:
                # Update progress in orchestrator
                self.orchestrator.update_progress(task_index, completed=False, failed=True)
                print(f"[Worker] Moving to next task after failure: {self.current_workflow.tasks[task_index + 1].title}")
                print(f"[Worker] Task {task_index + 2}/{len(self.current_workflow.tasks)}")  # Display in one-based
            else:
                # Last task failed
                await self.send_to_websocket("\nAuto Browser: Workflow completed with some failed tasks. Let me know if you need anything else.")
                self.current_workflow = None
            
            return "Task marked as failed, continuing with next task"
            
        except Exception as e:
            error_msg = f"Error marking task failed: {str(e)}"
            print(f"[Worker] {error_msg}")
            return error_msg

    async def display_message(self, message: str) -> str:
        """Display a message to the user in the chat."""
        try:
            await self.send_to_websocket(f"\nAuto Browser: {message}")
            return "Message displayed successfully"
        except Exception as e:
            return f"Error displaying message: {str(e)}"

    async def initialize(self):
        """Initialize the worker and send ready message."""
        await self.setup_client()