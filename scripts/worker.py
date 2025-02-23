import os
import time
import json
import base64
import sys
import traceback
import asyncio
import queue  # Added this import
from queue import Queue
from playwright.async_api import async_playwright, Page, ElementHandle
from openai import AsyncOpenAI
# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.web import get_page_elements, get_focused_element_info, get_main_content
from tools import *
from metrics import *
from messages import *
from handler import *

class Worker:
    def __init__(self, page: Page, worker_id: int, request_queue: Queue, api: str, model: str, max_messages: int):
        self.page = page
        self.worker_id = worker_id
        self.request_queue = request_queue
        self.input_queue = Queue()  # Worker-specific input queue
        self.api = api
        self.MODEL = model
        self.MAX_MESSAGES = max_messages
        self.active_element = None
        self.done = True
        self.waiting_for_input = False
        self.element_cache = {}
        self.client = None
        self.last_time = time.time()

        custom_instructions = ""
        try:
            with open("scripts/custom.log", "r") as f:
                custom_instructions = f.read()
            print(f"Worker {self.worker_id} Custom: {custom_instructions}")
        except:
            print(f"Worker {self.worker_id}: No custom instructions")

        WORKER_SYSTEM_PROMPT = f'''You are a helpful assistant designed to perform web actions via tools.

Here are the tools provided to you:
- move_to_url: Set a specific url as the active page.
- get_url_contents: Get the contents from the active page. Required when a new url is opened or changes are made to the page.
- send_keys_to_element: Send keys to page HTML element (for eg. to input text). Requires the xpath selector.
- submit: Submit the HTML element (for eg. to submit an input form). Requires the xpath selector.
- click_element: Click HTML element. Requires the xpath selector.
- highlight_element: Highlight HTML element. Requires the xpath selector.
- move_and_click_at_page_position: Move to page location and click.

When passing the xpathSelector argument, always use the selector provided in the JSON. 
If there are multiple selectors available, pick selector required from the error message provided.

An example query and actions:
User: Can you check who won the world cup yesterday?
Actions:    
- Open the Google homepage (move_to_url)
- Get the HTML contents of the page (get_url_contents)
- Set the search bar as the active element (set_element)
- Send Keys "Who won the world cup yesterday?" to the search bar (send_keys_to_element)
- Call submit on the search bar (call_submit). This will take you to the search results page.
- Get the HTML contents of the page (get_url_contents)
- Open the page that is more likely to have the answer (move_to_url/ click_element)
- Read the contents and output the answer to the question.

{custom_instructions}
'''
        print(f"Worker {self.worker_id} System Prompt:\n{WORKER_SYSTEM_PROMPT}")
        self.messages = MessageHistory(WORKER_SYSTEM_PROMPT)

    async def setup_client(self):
        api_key = os.environ.get('XAI_API_KEY')
        if api_key is None and self.api == "xai":
            print(f"Worker {self.worker_id}: XAI_API_KEY environment variable not set.")
            sys.exit(1)
        if self.api == "openai":
            self.client = AsyncOpenAI()
        elif self.api == "xai":
            self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        elif self.api == "ollama":
            self.client = AsyncOpenAI(api_key="____", base_url='http://localhost:11434/v1')

    async def move_to_url(self, url):
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            print(f"Worker {self.worker_id} Page: {url}")
            self.element_cache = {}
            elements = await get_page_elements(self.page)
            elements_info = await process(self, elements)  # Changed to await process
            contents = await self.get_url_contents()
            return f"Current page set to {url}. Page contents: {contents}"
        except Exception as e:
            error_msg = str(e)
            return f"Worker {self.worker_id} Error navigating to URL: {error_msg}"

    async def get_url_contents(self):
        cache_key = self.page.url
        if cache_key in self.element_cache:
            return self.element_cache[cache_key]
        time_start = time.time()
        try:
            await asyncio.sleep(4)
            await self.page.wait_for_load_state(state="domcontentloaded")
            content = await self.page.content()
            with open(f"log/page_{self.worker_id}.log", "w", encoding="utf-8") as f:
                f.write(content)
            elements = await get_page_elements(self.page)
            elements_info = await process(self, elements)  # Changed to await process
            main_content = await get_main_content(self.page)
            data = f"***PAGE JSON***\n\n{elements_info}\n\n{main_content}\n\n ***END OF PAGE JSON***"
            with open(f"log/last_{self.worker_id}.log", "w", encoding='utf-8') as f:
                f.write(data)
            print(f"Worker {self.worker_id} time (get page): {time.time() - time_start}")
            if len(data) > 20000:
                print(f"Worker {self.worker_id}: JSON TOO BIG")
            self.element_cache[cache_key] = data
            return data
        except Exception as e:
            print(f"Worker {self.worker_id} Error getting Page contents: {e}")
            return "Error retrieving page contents"

    async def send_keys_to_element(self, xpathSelector, keys: str):
        selector = f"xpath={xpathSelector}"
        locator = await self.get_locator(selector)
        active_element = locator[0]
        error_msg = locator[1]
        if error_msg is not None:
            return error_msg
        if active_element:
            try:
                await active_element.click(force=True)
                await active_element.fill("")
            except Exception as e:
                return f"Worker {self.worker_id} Error: {e}"
            try:
                await self.highlight_element(xpathSelector)
                await active_element.type(keys, delay=10)
                await asyncio.sleep(2)
                contents = await self.get_url_contents()
                return f"Worker {self.worker_id}: Keys sent to element. Page Contents: {contents}"
            except Exception as e:
                return f"Worker {self.worker_id} Error sending keys to element: {str(e)}"
        return "Invalid element."

    async def highlight_element(self, xpathSelector, highlight_color='red', duration=5000, gfirst=False):
        try:
            selector = f"xpath={xpathSelector}"
            locator = await self.get_locator(selector, gfirst)
            active_element = locator[0]
            error_msg = locator[1]
            if error_msg is not None:
                return error_msg
            bounding_box = await active_element.bounding_box()
            if bounding_box:
                box_data = {'box': bounding_box, 'color': highlight_color, 'duration': duration}
                await self.page.evaluate('''
                    (data) => {
                        const div = document.createElement('div');
                        div.style.cssText = `position:absolute;z-index:9999;border:4px solid ${data.color};pointer-events:none;`;
                        div.style.left = `${data.box.x + window.scrollX}px`;
                        div.style.top = `${data.box.y + window.scrollY}px`;
                        div.style.width = `${data.box.width}px`;
                        div.style.height = `${data.box.height}px`;
                        document.body.appendChild(div);
                        setTimeout(() => {
                            if (div && div.parentNode) {
                                div.parentNode.removeChild(div);
                            }
                        }, data.duration);
                    }
                ''', box_data)
            else:
                print(f"Worker {self.worker_id}: Could not get bounding box for the element.")
            return "Highlighted element"
        except Exception as e:
            print(f"Worker {self.worker_id} Error highlighting element: {e}")
            return f"Error highlighting element: {str(e)}"

    async def call_submit(self, xpathSelector):
        try:
            selector = f"xpath={xpathSelector}"
            locator = await self.get_locator(selector)
            active_element = locator[0]
            error_msg = locator[1]
            if error_msg is not None:
                return error_msg
            if active_element:
                form = await active_element.evaluate("el => el.closest('form')")
                if form:
                    await active_element.evaluate("el => el.form.submit()")
                else:
                    await active_element.press('Enter')
                return f"Worker {self.worker_id}: Successfully called submit on active element"
            return "No element to submit"
        except Exception as e:
            return f"Worker {self.worker_id} Error submitting form: {str(e)}"

    async def move_and_click_at_page_position(self, location_x, location_y):
        try:
            await self.page.mouse.move(location_x, location_y)
            await self.page.mouse.click(location_x, location_y)
            return f"Worker {self.worker_id}: Successfully moved to and clicked at coordinates: ({location_x}, {location_y})"
        except Exception as e:
            return f"Worker {self.worker_id}: An error occurred while moving and clicking at ({location_x}, {location_y}): {e}"

    async def click_element(self, xpathSelector):
        try:
            selector = f"xpath={xpathSelector}"
            locator = await self.get_locator(selector)
            active_element = locator[0]
            error_msg = locator[1]
            if error_msg is not None:
                return error_msg
            if active_element:
                try:
                    await active_element.scroll_into_view_if_needed(timeout=2000)
                except:
                    pass
                await self.highlight_element(xpathSelector)
                await active_element.click(force=True)
                await asyncio.sleep(3)
                contents = await self.get_url_contents()
                return f"Worker {self.worker_id}: Clicked element. Url Contents: {contents}"
            return "Element is invalid. Ensure that a correct HTML element is selected."
        except Exception as e:
            error_message = f"Worker {self.worker_id} Error clicking element: {str(e)}"
            print(error_message)
            print(f"Worker {self.worker_id} Stack trace:", traceback.format_exc())
            return error_message

    async def get_locator(self, selector, gfirst=False):
        error_msg = "Invalid XPath Selector. Recheck the selector arguments, text content and case sensitivity."
        time_start = time.time()
        try:
            count = await self.page.locator(selector).count()
            ret = None
            if count == 0:
                ret = error_msg
            locator = self.page.locator(selector)
            if count > 1:
                if gfirst:
                    locator = (await locator.all())[0]
                else:
                    all_locators = await locator.all()
                    ret = f"Multiple locators found. Call the tool with the appropriate selector with >> n notation from the list:\n{all_locators}"
            try:
                await locator.scroll_into_view_if_needed(timeout=100)
            except Exception:
                pass
            if ret is not None:
                print(f"Worker {self.worker_id} Error getting locator: {ret}")
            print(f"Worker {self.worker_id} time (locator): {time.time() - time_start}")
            return [locator, ret]
        except Exception as e:
            print(f"Worker {self.worker_id} Error in get_locator: {e}")
            return [None, str(e)]

    async def step(self):
        """Run one iteration of the worker loop, returning True if still active, False if done."""
        if self.client is None:
            await self.setup_client()

        tool_dict = {
            "move_to_url": self.move_to_url,
            "get_url_contents": self.get_url_contents,
            "send_keys_to_element": self.send_keys_to_element,
            "call_submit": self.call_submit,
            "click_element": self.click_element,
            "highlight_element": self.highlight_element,
            "move_and_click_at_page_position": self.move_and_click_at_page_position
        }

        curr_time = time.time()

        if self.done:
            if not self.waiting_for_input:
                print(f"Worker {self.worker_id} awaiting user input...")
                self.request_queue.put(self.worker_id)
                self.waiting_for_input = True

            try:
                user_input = self.input_queue.get_nowait()
                if user_input.lower() == 'quit':
                    return False
                print(f"{self.worker_id} received user input")
                self.done = False
                self.waiting_for_input = False
                self.messages.add_user_text(user_input)
                response = await self.client.chat.completions.create(
                    model=self.MODEL,
                    messages=self.messages.get_messages_for_api(),
                    tools=functions,
                    tool_choice="auto",
                    temperature=0.0,
                    parallel_tool_calls=False
                )
                print(f"Worker {self.worker_id} Response: {response}")
                print(f"Worker {self.worker_id} Content: {response.choices[0].message.content}")

                if response.choices[0].message.content and len(response.choices[0].message.content.strip()) > 0:
                    self.messages.add_assistant_text(response.choices[0].message.content)

                if response.choices[0].message.tool_calls:
                    for tool_call in response.choices[0].message.tool_calls:
                        function_name = tool_call.function.name
                        print(f"Worker {self.worker_id} Call: {function_name}")
                        function_args = json.loads(tool_call.function.arguments)
                        result = await tool_dict[function_name](**function_args)
                        print(f"Worker {self.worker_id} Result: {result}")
                        self.messages.add_tool_call(tool_call.id, function_name, tool_call.function.arguments)
                        self.messages.add_tool_response(tool_call.id, result, function_name)
                        break
                else:
                    self.done = True
            except queue.Empty:
                pass  # Still waiting for input

        elif self.api != "ollama":
            await self.page.screenshot(path=f'browser_{self.worker_id}.jpeg', type="jpeg", full_page=False, quality=100)
            self.messages.add_user_with_image("Browser snapshot", f"browser_{self.worker_id}.jpeg")
            response = await self.client.chat.completions.create(
                model=self.MODEL,
                messages=self.messages.get_messages_for_api(),
                tools=functions,
                tool_choice="auto",
                temperature=0.0,
                parallel_tool_calls=False
            )
            print(f"Worker {self.worker_id} Response: {response}")
            print(f"Worker {self.worker_id} Content: {response.choices[0].message.content}")

            if response.choices[0].message.content and len(response.choices[0].message.content.strip()) > 0:
                self.messages.add_assistant_text(response.choices[0].message.content)

            if response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    function_name = tool_call.function.name
                    print(f"Worker {self.worker_id} Call: {function_name}")
                    function_args = json.loads(tool_call.function.arguments)
                    result = await tool_dict[function_name](**function_args)
                    print(f"Worker {self.worker_id} Result: {result}")
                    self.messages.add_tool_call(tool_call.id, function_name, tool_call.function.arguments)
                    self.messages.add_tool_response(tool_call.id, result, function_name)
                    break
            else:
                self.done = True

        self.last_time = curr_time
        elapsed_time = curr_time - self.last_time
        print(f"Worker {self.worker_id} Elapsed: {elapsed_time:.2f}s")
        self.messages.trim_history(max_messages=self.MAX_MESSAGES)
        return True
