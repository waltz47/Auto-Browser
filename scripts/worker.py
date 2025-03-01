import os
import time
import json
import asyncio
from playwright.async_api import Page
from openai import AsyncOpenAI
from typing import Dict, Any

# Assuming these imports remain necessary from your project structure
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web import *
from tools import *
from metrics import *
from messages import *
from handler import *

class Worker:
    def __init__(self, page: Page, worker_id: int, request_queue, api: str, model: str, max_messages: int):
        """Initialize a worker with a browser page and configuration."""
        self.page = page
        self.worker_id = worker_id
        self.request_queue = request_queue  # Sync queue for signaling input need
        self.input_queue = None  # Will be set to asyncio.Queue by Nyx
        self.api = api
        self.model = model
        self.max_messages = max_messages
        self.element_cache: Dict[str, str] = {}
        self.client = None
        self.messages = self._init_message_history()
        self.is_running = True
        self.waiting_for_input = False

    def _init_message_history(self) -> MessageHistory:
        """Initialize the message history with system prompt."""
        try:
            with open("scripts/custom.log", "r") as f:
                custom_instructions = f.read()
        except FileNotFoundError:
            custom_instructions = ""
            print(f"Worker {self.worker_id}: No custom instructions")

        system_prompt = f'''You are a helpful assistant designed to perform web actions via tools.

Available tools:
- move_to_url: Navigate to a specific URL.
- get_url_contents: Retrieve current page contents.
- send_keys_to_element: Input text into an element (requires xpath).
- call_submit: Submit a form (requires xpath).
- click_element: Click an element (requires xpath).
- highlight_element: Highlight an element (requires xpath).
- move_and_click_at_page_position: Click at specific coordinates.

Use provided xpath selectors from JSON data. For multiple matches, select based on context or error hints.

Example:
Query: "Check yesterday's World Cup winner"
Steps:
1. move_to_url("https://google.com")
2. get_url_contents()
3. send_keys_to_element(search bar xpath, "Who won the World Cup yesterday?")
4. call_submit(search bar xpath)
5. get_url_contents()
6. click_element(result link xpath)
7. get_url_contents() and extract answer

{custom_instructions}'''
        print(f"Worker {self.worker_id} System Prompt:\n{system_prompt}")
        return MessageHistory(system_prompt)

    async def setup_client(self):
        """Set up the OpenAI client based on API configuration."""
        api_key = os.environ.get('XAI_API_KEY')
        if self.api == "xai" and not api_key:
            print(f"Worker {self.worker_id}: XAI_API_KEY not set.")
            sys.exit(1)
        if self.api == "openai":
            self.client = AsyncOpenAI()
        elif self.api == "xai":
            self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        elif self.api == "ollama":
            self.client = AsyncOpenAI(api_key="____", base_url='http://localhost:11434/v1')

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

    async def move_and_click_at_page_position(self, x: float, y: float) -> str:
        """Move to and click at specific page coordinates."""
        try:
            await self.page.mouse.move(x, y)
            await self.page.mouse.click(x, y)
            return f"Worker {self.worker_id}: Clicked at ({x}, {y})"
        except Exception as e:
            return f"Worker {self.worker_id} Error clicking at ({x}, {y}): {str(e)}"

    async def _get_locator(self, xpathSelector: str, first_only=False) -> tuple[Any, str]:
        """Retrieve a locator for an xpath, handling multiple matches."""
        selector = f"xpath={xpathSelector}"
        try:
            locator = self.page.locator(selector)
            count = await locator.count()
            if count == 0:
                return None, "Invalid XPath: No elements found"
            if count > 1 and not first_only:
                return None, f"Multiple elements found for {selector}. Specify with >> n notation"
            if first_only:
                locator = locator.first
            return locator, None
        except Exception as e:
            return None, f"Error getting locator: {str(e)}"

    async def step(self) -> bool:
        """Execute one step of the worker's operation."""
        if not self.client:
            await self.setup_client()

        tools = {
            "move_to_url": self.move_to_url,
            "get_url_contents": self.get_url_contents,
            "send_keys_to_element": self.send_keys_to_element,
            "call_submit": self.call_submit,
            "click_element": self.click_element,
            "highlight_element": self.highlight_element,
            "move_and_click_at_page_position": self.move_and_click_at_page_position
        }

        # Request input if not waiting or running
        if not self.waiting_for_input and not self.is_running:
            print(f"Worker {self.worker_id} awaiting input...")
            self.request_queue.put(self.worker_id)
            self.waiting_for_input = True
            await asyncio.sleep(0.1)  # Ensure queue is processed
            return True

        # Process input if waiting
        if self.waiting_for_input:
            try:
                print(f"Worker {self.worker_id} waiting for input, queue size: {self.input_queue.qsize()}")
                user_input = await self.input_queue.get()
                print(f"Worker {self.worker_id} got input: {user_input}")
                if user_input.lower() == "quit":
                    print(f"Worker {self.worker_id} quitting")
                    return False
                self.waiting_for_input = False
                self.is_running = True
                self.messages.add_user_text(user_input)

                # Add screenshot with initial input
                if self.api != "ollama":
                    await self.page.screenshot(path=f'snaps/browser_{self.worker_id}.jpeg', type="jpeg", full_page=False, quality=100)
                    self.messages.add_user_with_image("Browser snapshot", f"snaps/browser_{self.worker_id}.jpeg")

                # Initial API call after input
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages.get_messages_for_api(),
                    tools=functions,
                    tool_choice="auto",
                    temperature=0.0,
                    parallel_tool_calls=False
                )
                content = response.choices[0].message.content
                print(f"Worker {self.worker_id} Response: {content}")

                if content:
                    self.messages.add_assistant_text(content)

                if response.choices[0].message.tool_calls:
                    tool_call = response.choices[0].message.tool_calls[0]
                    function_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    result = await tools[function_name](**args)
                    print(f"Worker {self.worker_id} Tool result: {result}")
                    self.messages.add_tool_call(tool_call.id, function_name, tool_call.function.arguments)
                    self.messages.add_tool_response(tool_call.id, result, function_name)
                else:
                    self.is_running = False
                    self.waiting_for_input = False  # Reset to request input

            except Exception as e:
                print(f"Worker {self.worker_id} Error processing input: {e}")
                self.is_running = False
                self.waiting_for_input = False
                await asyncio.sleep(0.1)
                return True

        # Continue multi-step execution if running
        elif self.is_running:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages.get_messages_for_api(),
                    tools=functions,
                    tool_choice="auto",
                    temperature=0.0,
                    parallel_tool_calls=False
                )
                content = response.choices[0].message.content
                print(f"Worker {self.worker_id} Response: {content}")

                if content:
                    self.messages.add_assistant_text(content)

                if response.choices[0].message.tool_calls:
                    tool_call = response.choices[0].message.tool_calls[0]
                    function_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    result = await tools[function_name](**args)
                    print(f"Worker {self.worker_id} Tool result: {result}")
                    self.messages.add_tool_call(tool_call.id, function_name, tool_call.function.arguments)
                    self.messages.add_tool_response(tool_call.id, result, function_name)
                else:
                    self.is_running = False
                    self.waiting_for_input = False  # Reset to request input

            except Exception as e:
                print(f"Worker {self.worker_id} Error in multi-step execution: {e}")
                self.is_running = False
                self.waiting_for_input = False
                await asyncio.sleep(0.1)
                return True

        self.messages.trim_history(max_messages=self.max_messages)
        await asyncio.sleep(0.1)  # Prevent tight looping
        return True