import os
import time
import json
import asyncio
from playwright.async_api import Page
from openai import AsyncOpenAI
from typing import Dict, Any
import base64
import traceback

# Assuming these imports remain necessary from your project structure
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web import *
from tools import functions as web_tools  # Import web tools from tools.py
from metrics import *
from messages import *
from handler import *

class Worker:
    def __init__(self, page: Page, worker_id: int, request_queue, api: str, model: str, max_messages: int, tools=None):
        """Initialize a worker with a browser page and configuration."""
        self.page = page
        self.worker_id = worker_id
        self.request_queue = request_queue  # Sync queue for signaling input need
        self.input_queue = None  # Will be set to asyncio.Queue by Nyx
        self.error_queue = None  # Will be set to asyncio.Queue by Nyx for error reporting
        self.api = api
        self.model = model
        self.max_messages = max_messages
        self.element_cache: Dict[str, str] = {}
        self.client = None
        self.is_running = True
        self.waiting_for_input = False
        self.current_task = "Initializing"  # Initialize current_task before creating message history
        self.error_state = None
        self.tools = tools or []  # Initialize tools with provided tools or empty list
        self.api_call_attempts = 0  # Initialize counter for API call attempts
        self.processed_tool_call_ids = []  # Initialize tracking for processed tool call IDs
        self.messages = self._init_message_history()  # Now call _init_message_history after current_task is set

    def set_queues(self, input_queue, error_queue):
        """Set the input and error queues for the worker."""
        self.input_queue = input_queue
        self.error_queue = error_queue

    def _init_message_history(self) -> MessageHistory:
        """Initialize the message history with system prompt."""
        try:
            with open("scripts/custom.log", "r") as f:
                custom_instructions = f.read()
        except FileNotFoundError:
            custom_instructions = ""
            print(f"Worker {self.worker_id}: No custom instructions")

        # Define the available tools for the worker
        tools_description = """
You have access to the following tools to help you navigate and interact with web pages:

1. move_to_url(url: str) - Navigate to a specific URL
2. get_url_contents() - Get the contents of the current page
3. send_keys_to_element(xpathSelector: str, keys: str) - Send text to an element
4. call_submit(xpathSelector: str) - Submit a form
5. click_element(xpathSelector: str) - Click on an element
6. highlight_element(xpathSelector: str) - Highlight an element for visibility
7. move_and_click_at_page_position(x: float, y: float) - Click at specific coordinates

When you complete your task, include "TASK_COMPLETE" in your response.
If you need user input, include "WAITING_FOR_INPUT" in your response.
"""

        # Get current task with a fallback for safety
        current_task = getattr(self, 'current_task', "Not yet specified")

        system_prompt = f'''You are a general purpose AI agent capable of performing web-based tasks. You can browse websites, search for information, and interact with web elements.

Your current task is: {current_task}

Instructions for completing tasks:
1. Always start by navigating to a relevant website using move_to_url
2. After each navigation, use get_url_contents to analyze the page
3. Use other tools as needed to navigate and interact with elements
4. Be thorough and methodical in your task completion
5. Include "TASK_COMPLETE" only when you've successfully completed your task
6. If you need additional information or user input, include "WAITING_FOR_INPUT"

{tools_description}

{custom_instructions}'''
        print(f"Worker {self.worker_id} initialized with general purpose configuration")
        return MessageHistory(system_prompt)

    async def setup_client(self):
        """Set up the OpenAI client based on API configuration."""
        try:
            if self.client is not None:
                return  # Client already initialized
                
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
                
            print(f"Worker {self.worker_id}: API client initialized successfully")
        except Exception as e:
            error_msg = f"Failed to initialize API client: {str(e)}"
            print(f"Worker {self.worker_id}: {error_msg}")
            await self.report_error('api_initialization_error', error_msg)
            raise

    async def move_to_url(self, url: str) -> str:
        """Navigate to a URL and return page contents."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            print(f"Worker {self.worker_id} Navigated to: {url}")
            self.element_cache.clear()
            return f"Navigated to {url}. Contents: {await self.get_url_contents()}"
        except Exception as e:
            return f"Worker {self.worker_id} Error navigating to URL: {str(e)}"

    async def get_url_contents(self) -> str:
        """Retrieve and cache the current page's contents."""
        cache_key = self.page.url
        if cache_key in self.element_cache:
            return self.element_cache[cache_key]
        
        try:
            await asyncio.sleep(4)
            await self.page.wait_for_load_state(state="domcontentloaded")
            content = await self.page.content()
            with open(f"log/page_{self.worker_id}.log", "w", encoding="utf-8") as f:
                f.write(content)
            
            elements = await get_page_elements(self.page)
            elements_info = await process(self, elements)
            main_content = await get_main_content(self.page)
            data = f"***PAGE JSON***\n\n{elements_info}\n\n{main_content}\n\n ***END OF PAGE JSON***"
            
            with open(f"log/last_{self.worker_id}.log", "w", encoding="utf-8") as f:
                f.write(data)
            if len(data) > 20000:
                print(f"Worker {self.worker_id}: JSON TOO BIG")
            self.element_cache[cache_key] = data
            return data
        except Exception as e:
            print(f"Worker {self.worker_id} Error getting page contents: {e}")
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
            return f"Worker {self.worker_id}: Keys sent. Contents: {await self.get_url_contents()}"
        except Exception as e:
            return f"Worker {self.worker_id} Error sending keys: {str(e)}"

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
            return f"Worker {self.worker_id}: Form submitted"
        except Exception as e:
            return f"Worker {self.worker_id} Error submitting form: {str(e)}"

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
            return f"Worker {self.worker_id}: Element clicked. Contents: {await self.get_url_contents()}"
        except Exception as e:
            return f"Worker {self.worker_id} Error clicking element: {str(e)}"

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
            print(f"Worker {self.worker_id} Error highlighting: {e}")
            return "Error highlighting element"

    async def move_and_click_at_page_position(self, x=None, y=None, location_x=None, location_y=None) -> str:
        """Move to and click at specific page coordinates.
        
        Supports both parameter formats:
        - x, y (from tools.py)
        - location_x, location_y (from older formats)
        """
        try:
            # Use whichever parameters are provided
            x_coord = x if x is not None else location_x
            y_coord = y if y is not None else location_y
            
            if x_coord is None or y_coord is None:
                return f"Worker {self.worker_id}: Error - Missing coordinates for clicking"
                
            await self.page.mouse.move(x_coord, y_coord)
            await self.page.mouse.click(x_coord, y_coord)
            return f"Worker {self.worker_id}: Clicked at ({x_coord}, {y_coord})"
        except Exception as e:
            return f"Worker {self.worker_id} Error clicking at position: {str(e)}"

    async def _get_locator(self, xpathSelector: str, first_only=False) -> tuple[Any, str]:
        """Retrieve a locator for an xpath, handling multiple matches."""
        selector = f"xpath={xpathSelector}"
        try:
            locator = self.page.locator(selector)
            count = await locator.count()
            if (count == 0):
                return None, "Invalid XPath: No elements found"
            if (count > 1 and not first_only):
                return None, f"Multiple elements found for {selector}. Specify with >> n notation"
            if first_only:
                locator = locator.first
            return locator, None
        except Exception as e:
            return None, f"Error getting locator: {str(e)}"

    async def report_error(self, error_type: str, error_message: str):
        """Report an error to the orchestrator."""
        if self.error_queue:
            error_data = {
                'worker_id': self.worker_id,
                'error_type': error_type,
                'error_message': error_message,
                'task': self.current_task,
                'timestamp': time.time()
            }
            await self.error_queue.put(error_data)
            self.error_state = error_data
        else:
            print(f"Worker {self.worker_id}: Error queue not set, cannot report error: {error_message}")

    async def step(self) -> bool:
        """Execute one step of the worker's task."""
        try:
            if not self.input_queue:
                await self.report_error('configuration_error', 'Input queue not set')
                return False
                
            if self.waiting_for_input:
                if self.input_queue.empty():
                    self.request_queue.put(self.worker_id)
                    await asyncio.sleep(0.1)
                    return True
                    
                user_input = await self.input_queue.get()
                self.waiting_for_input = False
                self.current_task = user_input
                print(f"Worker {self.worker_id} received input: {user_input}")
                # Add the user input to the message history
                self.messages.add_user_text(user_input)
                return True  # Return after getting input to process it in next step
                
            # Add a retry counter to prevent infinite loops
            if not hasattr(self, 'api_call_attempts'):
                self.api_call_attempts = 0
                
            # If we've tried too many times with failures, force waiting for input
            if self.api_call_attempts > 3:
                print(f"Worker {self.worker_id}: Too many API call attempts, requesting user input")
                self.waiting_for_input = True
                self.api_call_attempts = 0
                self.messages.add_assistant_message("I'm having trouble with this task. WAITING_FOR_INPUT - Please provide more specific instructions.")
                return True
            
            try:
                print(f"Worker {self.worker_id}: Sending messages to API (attempt {self.api_call_attempts + 1})")
                self.api_call_attempts += 1
                
                # If no tools provided, use web_tools from tools.py
                if not self.tools:
                    print(f"Worker {self.worker_id}: No tools provided, using web_tools from tools.py")
                    self.tools = web_tools
                
                # Use non-streaming API call for simplicity
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages.get_messages_for_api(),
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=0.7,
                    stream=False  # Non-streaming mode
                )
                
                # API call succeeded, reset the attempts counter
                self.api_call_attempts = 0
                
                # Extract content and tool calls from the complete response
                content = response.choices[0].message.content or ""
                tool_calls = response.choices[0].message.tool_calls or []
                
                print(f"Worker {self.worker_id}: Received response with {len(content)} chars content and {len(tool_calls)} tool calls")
                
                # Process the response if it has content or tool calls
                if content or tool_calls:
                    # First, add the assistant message with content and tool calls
                    if tool_calls:
                        # Create message with both content and tool calls
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
                    else:
                        # No tool calls, just add the content
                        self.messages.add_assistant_message(content)
                    
                    # Process tool calls if present
                    valid_tool_calls = False
                    
                    # Track IDs processed in this round
                    current_round_ids = []
                    
                    for tool_call in tool_calls:
                        tool_call_id = tool_call.id
                        function_name = tool_call.function.name
                        arguments = tool_call.function.arguments
                        
                        # Skip if we've already processed this tool call ID
                        if tool_call_id in self.processed_tool_call_ids:
                            print(f"Worker {self.worker_id}: Skipping already processed tool call {tool_call_id}")
                            continue
                            
                        # Track this ID for processing
                        current_round_ids.append(tool_call_id)
                        
                        # Handle missing arguments with defaults based on function
                        if not arguments or arguments.strip() == '':
                            print(f"Worker {self.worker_id}: Missing arguments in tool call: {tool_call}")
                            
                            # Provide default arguments based on function name
                            if function_name == "get_url_contents":
                                arguments = "{}"
                                print(f"Worker {self.worker_id}: Using empty arguments for {function_name}")
                            elif function_name == "move_to_url":
                                # If move_to_url has empty args, we can't proceed - add an error response
                                error_result = f"Error: The move_to_url function requires a URL parameter. Please provide a valid URL."
                                self.messages.add_tool_response(tool_call_id, error_result, function_name)
                                continue
                            else:
                                # For other functions, add an error response
                                error_result = f"Error: Missing arguments for {function_name}. Please provide valid arguments."
                                self.messages.add_tool_response(tool_call_id, error_result, function_name)
                                continue
                            
                        print(f"Worker {self.worker_id} executing tool: {function_name}, args len: {len(arguments)}")
                        
                        # Execute the tool function
                        if hasattr(self, function_name):
                            try:
                                tool_function = getattr(self, function_name)
                                print(f"Worker {self.worker_id}: Parsing arguments for {function_name}: {arguments}")
                                
                                # Ensure arguments is valid JSON
                                args_dict = json.loads(arguments)
                                print(f"Worker {self.worker_id}: Executing {function_name} with args: {args_dict}")
                                
                                result = await tool_function(**args_dict)
                                print(f"Worker {self.worker_id}: Tool {function_name} executed successfully")
                                
                                # Add tool response to message history
                                self.messages.add_tool_response(tool_call_id, result, function_name)
                                
                                # Mark that we've successfully executed at least one tool
                                valid_tool_calls = True
                                
                            except json.JSONDecodeError as je:
                                error_msg = f"Invalid JSON in tool arguments: {arguments} - Error: {str(je)}"
                                print(f"Worker {self.worker_id}: {error_msg}")
                                # Add error response to continue the conversation
                                error_result = f"Error: Could not parse arguments for {function_name}. Please provide valid JSON."
                                self.messages.add_tool_response(tool_call_id, error_result, function_name)
                                continue
                            except TypeError as te:
                                error_msg = f"Type error executing tool {function_name} with args {args_dict if 'args_dict' in locals() else 'unknown'}: {str(te)}"
                                print(f"Worker {self.worker_id}: {error_msg}")
                                # Add error response to continue the conversation
                                error_result = f"Error executing {function_name}: {str(te)}. Please check argument types."
                                self.messages.add_tool_response(tool_call_id, error_result, function_name)
                                continue
                            except Exception as e:
                                error_msg = f"Error executing tool {function_name}: {str(e)}"
                                print(f"Worker {self.worker_id}: {error_msg}")
                                # Add error response to continue the conversation
                                error_result = f"Error executing {function_name}: {str(e)}"
                                self.messages.add_tool_response(tool_call_id, error_result, function_name)
                                continue
                        else:
                            error_msg = f"Function {function_name} not found"
                            print(f"Worker {self.worker_id}: {error_msg}")
                            # Add error response to continue the conversation
                            error_result = f"Error: Function {function_name} is not available."
                            self.messages.add_tool_response(tool_call_id, error_result, "error")
                    
                    # Update processed tool calls - only add the ones we successfully handled this round
                    self.processed_tool_call_ids.extend(current_round_ids)
                    print(f"Worker {self.worker_id}: Updated processed_tool_call_ids, now tracking {len(self.processed_tool_call_ids)} IDs")
                    
                    # If no valid tool calls and no meaningful content, request user input after repeated failures
                    if not valid_tool_calls and not content:
                        self.api_call_attempts += 1  # Increase attempt counter
                        print(f"Worker {self.worker_id}: No valid tool calls or content, attempt {self.api_call_attempts}")
                    
                    # Only check for task completion markers if there's content
                    if content:
                        # Check if task is complete
                        if "TASK_COMPLETE" in content:
                            print(f"Worker {self.worker_id} completed task")
                            return False
                        
                        # Set waiting for input flag for next iteration if needed
                        if "WAITING_FOR_INPUT" in content:
                            self.waiting_for_input = True
                    
                    return True
                else:
                    print(f"Worker {self.worker_id}: Empty response, attempt {self.api_call_attempts}")
                    # If we get empty responses repeatedly, request user input
                    if self.api_call_attempts >= 3:
                        print(f"Worker {self.worker_id}: Too many empty responses, requesting user input")
                        self.waiting_for_input = True
                        self.api_call_attempts = 0
                        self.messages.add_assistant_message("I'm having trouble completing this task. WAITING_FOR_INPUT - Please provide more specific instructions or a different URL to explore.")
                        return True
                    
                    await self.report_error('api_error', 'Empty response from API (no content or tool calls)')
                    return True  # Continue processing despite error to avoid aborting the worker
                
            except Exception as e:
                await self.report_error('api_error', f'Error in API call: {str(e)}')
                traceback.print_exc()  # Add traceback for better debugging
                return True  # Continue processing despite error
                
        except Exception as e:
            await self.report_error('execution_error', f'Error during execution: {str(e)}')
            traceback.print_exc()  # Add traceback for better debugging
            return False