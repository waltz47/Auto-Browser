import os
import time
import json
import asyncio
from playwright.async_api import Page
from openai import AsyncOpenAI
from typing import Dict, Any
import traceback

# Import web tools and messages
from web.web import get_page_elements, get_main_content
from web.handler import process, test_selectors_on_page, enhance_json_with_selectors
from tools import functions as web_tools
from messages import MessageHistory, Message

class Worker:
    def __init__(self, page: Page, worker_id: int, request_queue, api: str, model: str, max_messages: int, tools=None, websocket=None):
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
        self.tools = tools or web_tools  # Use provided tools or default to web_tools
        self.messages = self._init_message_history()
        self.websocket = websocket  # Add websocket support

    def _init_message_history(self) -> MessageHistory:
        """Initialize the message history with system prompt."""
        try:
            with open("scripts/custom.log", "r") as f:
                custom_instructions = f.read()
        except FileNotFoundError:
            custom_instructions = ""
            print("No custom instructions found")

        tools_description = """
IMPORTANT: You can ONLY use the following tools. Do not attempt to use any other functions:

1. move_to_url(url: str) - Navigate to a specific URL
2. get_url_contents() - Get the contents of the current page
3. send_keys_to_element(xpathSelector: str, keys: str) - Send text to an element
4. call_submit(xpathSelector: str) - Submit a form
5. click_element(xpathSelector: str) - Click on an element
6. highlight_element(xpathSelector: str) - Highlight an element for visibility
7. move_and_click_at_page_position(x: float, y: float) - Click at specific coordinates

Do not attempt to use any other functions that are not listed above. Functions like 'create_agent' are not available.
"""

        system_prompt = f'''You are a general purpose AI agent capable of performing web-based tasks. You can browse websites, search for information, and interact with web elements.

Instructions:
1. When you need to interact with the web, use ONLY the available tools listed below
2. When you need more information or clarification, ask the user directly
3. Be thorough and methodical in your responses
4. Maintain a natural conversation with the user
5. Do NOT suggest or try to use tools that are not explicitly listed
6. After completing a task or when waiting for user input, stop and wait for the next command

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

    async def move_to_url(self, url: str) -> str:
        """Navigate to a URL and return page contents."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            print(f"Navigated to: {url}")
            self.element_cache.clear()
            return f"Navigated to {url}. Contents: {await self.get_url_contents()}"
        except Exception as e:
            return f"Error navigating to URL: {str(e)}"

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
                return None, f"There are multiple elements found for the xpath selector: {selector}. Pick the required one with >> n selector notation"
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
            await self.websocket.send_text(message)
        else:
            # If no websocket, everything goes to terminal
            print(message)

    async def step(self) -> bool:
        """Execute one step of the worker's task."""
        try:
            # Print current messages for debugging (terminal only)
            await self.send_to_websocket("\n=== Current Messages ===", debug=True)
            for msg in self.messages.get_messages_for_api():
                await self.send_to_websocket(f"[{msg['role']}]: {msg['content'][:200]}...", debug=True)
            await self.send_to_websocket("=== End Messages ===\n", debug=True)

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

            # Process the response
            if content or tool_calls:
                # Add the assistant message
                if tool_calls:
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
                    
                    # Send content to websocket if available
                    if content:
                        await self.send_to_websocket(f"\nAssistant: {content}")
                    
                    # Process tool calls
                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        arguments = tool_call.function.arguments

                        if not arguments or arguments.strip() == '':
                            error_result = f"Error: Missing arguments for {function_name}"
                            await self.send_to_websocket(error_result, debug=True)
                            self.messages.add_tool_response(tool_call.id, error_result, function_name)
                            continue

                        # Execute the tool function
                        if hasattr(self, function_name):
                            try:
                                tool_function = getattr(self, function_name)
                                args_dict = json.loads(arguments)
                                result = await tool_function(**args_dict)
                                await self.send_to_websocket(f"Tool {function_name}: {result}", debug=True)
                                self.messages.add_tool_response(tool_call.id, result, function_name)
                            except Exception as e:
                                error_result = f"Error executing {function_name}: {str(e)}"
                                await self.send_to_websocket(error_result, debug=True)
                                self.messages.add_tool_response(tool_call.id, error_result, function_name)
                        else:
                            error_result = f"Error: Function {function_name} is not available"
                            await self.send_to_websocket(error_result, debug=True)
                            self.messages.add_tool_response(tool_call.id, error_result, "error")
                    
                    return True
                else:
                    # Send the message to websocket and wait for user input
                    await self.send_to_websocket(f"\nAssistant: {content}")
                    self.messages.add_assistant_message(content)
                    return False  # Stop here and wait for user input

            else:
                await self.send_to_websocket("Empty response from API", debug=True)
                return False

        except Exception as e:
            await self.send_to_websocket(f"Error in step: {e}", debug=True)
            traceback.print_exc()
            return False