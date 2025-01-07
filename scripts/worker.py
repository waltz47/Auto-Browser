import os
import time
import json
import base64
import sys
import traceback
from playwright.sync_api import sync_playwright, Page, ElementHandle
from playwright.sync_api import Page
from openai import OpenAI
from tools import *
from metrics import *
from web import *
from messages import *

class Worker:
    def __init__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.firefox.launch(headless=False)  # Set headless=True for production
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            locale="en-US",
            viewport={"width": 1920, "height": 1080},
            permissions=["geolocation"]
        )
        self.page = self.context.new_page()
        self.active_element = None
        self.done = True
        WORKER_SYSTEM_PROMPT = '''You are a helpful assistant designed to perform web actions via tools.

Here are the tools provided to you:
- move_to_url: Set a specific url as the active page.
- get_url_contents: Get the contents from the active page. Required when a new url is opened or changes are made to the page.
- set_active_element: Set a HTML page element as active via an xpath selector.
- send_keys_to_active_element: Send keys to page HTML element (for eg. to input text).
- submit: Submit the active HTML element (for eg. to submit an input form).
- click_active_element: Click active HTML element.
- highlight_active_element: Highlight active HTML element.

An example query and actions:
User: Can you check who won the world cup yesterday?
Actions:    
- Open the Google homepage (move_to_url)
- Get the HTML contents of the page (get_url_contents)
- Set the search bar as the active element (set_active_element)
- Send Keys "Who won the world cup yesterday?" to the search bar (send_keys_to_active_element)
- Call submit on the search bar (call_submit). This will take you to the search results page.
- Get the HTML contents of the page (get_url_contents)
- Open the page that is more likely to have the answer (move_to_url/ set_active_element/ click_active_element)
- Read the contents and output the answer to the question.'''

        self.messages = MessageHistory(WORKER_SYSTEM_PROMPT)
        self.prev_state = ""

    def move_to_url(self, url):
        try:
            self.page.goto(url, wait_until="networkidle")
            time.sleep(1)
            return f"Current page set to {url}. Use `get_url_contents` to get the contents of the page."
        except Exception as e:
            return f"Error navigating to URL: {str(e)}"


    def get_url_contents(self):
        """Get clean, structured representation of page contents."""
        try:
            self.page.wait_for_load_state(state="networkidle")
            elements_info = get_page_elements(self.page)
            # elements_info = self.page.evaluate("""() => {
            #     setTimeout(() => {
            #         const overlays = document.querySelectorAll('div[style*="border: 2px dashed blue"]');
            #         overlays.forEach(overlay => overlay.remove());
            #     }, 8000); // 8 second timeout to remove overlays
            #     const getElements = () => {
            #         const elements = {
            #             inputs: [...document.querySelectorAll("input, textarea")],
            #             buttons: [...document.querySelectorAll("button, [role='button']")],
            #             links: [...document.querySelectorAll("a")]
            #         };
                    
            #         const result = {elements: {}};
            #         let counter = 1;
                    
            #         for (const [key, elemList] of Object.entries(elements)) {
            #             result.elements[key] = elemList.map(elem => {
            #                 const box = elem.getBoundingClientRect();
            #                 const info = {
            #                     tag: elem.tagName.toLowerCase(),
            #                     type: elem.type,
            #                     id: elem.id,
            #                     name: elem.name,
            #                     value: elem.value,
            #                     ariaLabel: elem.getAttribute('aria-label'),
            #                     role: elem.getAttribute('role'),
            #                     text: elem.innerText,
            #                     classes: elem.className,
            #                     elementNumber: counter,
            #                     /*bbox: {
            #                         x: box.x,
            #                         y: box.y,
            #                         width: box.width,
            #                         height: box.height
            #                     }*/
            #                 };
                            
            #                 const overlay = document.createElement('div');
            #                 overlay.style.cssText = `
            #                     position: fixed;
            #                     border: 2px dashed blue;
            #                     left: ${box.x}px;
            #                     top: ${box.y}px;
            #                     width: ${box.width}px;
            #                     height: ${box.height}px;
            #                     pointer-events: none;
            #                     z-index: 10000;
            #                 `;
                            
            #                 const num = document.createElement('div');
            #                 num.textContent = counter++;
            #                 num.style.cssText = `
            #                     position: absolute;
            #                     left: -20px;
            #                     top: -20px;
            #                     background: red;
            #                     color: white;
            #                     border-radius: 50%;
            #                     padding: 2px 6px;
            #                     font-size: 25px;
            #                 `;
                            
            #                 //overlay.appendChild(num);
            #                 document.body.appendChild(overlay);
                            
            #                 return info;
            #             });
            #         }
            #         return result;
            #     };
            #     return getElements();
            # }""")
            
            focused = get_focused_element_info(self.page)
            main_content = get_main_content(self.page)
            
            data = f"***PAGE JSON***\n\n{elements_info}\n\nFOCUSED ELEMENT:\n{json.dumps(focused, indent=2)}\n\n{main_content}\n\n ***END OF PAGE JSON***"
            
            self.prev_state = elements_info
            summarized = self.summarize(data)

            open("last.log","w",encoding='utf-8').write(data)
            return summarized
        except Exception as e:
            print("Error getting Page contents:", e)
            assert(0)

    def find_element_by(self, locator_type, locator_value, input_type=None):
        try:
            selector = self._get_selector(locator_type, locator_value)
            element = self.page.query_selector(selector)
            
            if element is None:
                return None
                
            if input_type and element.evaluate("el => el.tagName.toLowerCase()") == 'input':
                actual_type = element.get_attribute('type')
                if actual_type != input_type:
                    return None
                    
            return element
            
        except Exception as e:
            print(f"Error finding element: {e}")
            return None

    def _get_selector(self, locator_type, locator_value):
        selectors = {
            'id': f'#{locator_value}',
            'class': f'.{locator_value}',
            'name': f'[name="{locator_value}"]',
            'tag': locator_value,
            'link': f'a:has-text("{locator_value}")',
            'partial_link': f'a:has-text("{locator_value}")',
            'xpath': locator_value,  # Playwright supports xpath directly
            'css': locator_value,
            'ariaLabel': f'[aria-label="{locator_value}"]',
        }
        
        if locator_type.lower() not in selectors:
            print("Selector is None")
            raise ValueError(f"Unsupported locator type: {locator_type}. Available types are: {', '.join(selectors.keys())}")
            
        return selectors[locator_type.lower()]

    def set_active_element(self, xpath_selector: str):
        error_msg = """Invalid XPath Selector. Recheck the selector arguments, text content and case sensitivity."""

        print(f"Getting element with xpath selector: {xpath_selector}")
        try:
            # self.active_element = self.page.query_selector(xpath_selector)
            selector = f"xpath={xpath_selector}"
            count = self.page.locator(selector).count()

            if count == 0:
                return error_msg

            self.active_element = self.page.locator(selector)
            print(f"Focused: {self.active_element}")
            if self.active_element is None:
                return error_msg
            else:
                try:
                    self.active_element.scroll_into_view_if_needed()
                except:
                    pass
                self.highlight_active_element('black', 5000)
            # return f"Active element updated to element of class: {locator_value}"
            return "Active element updated."
        except Exception as e:
            return f"Error setting active element: {str(e)}"

    def send_keys_to_active_element(self, keys: str):
        if self.active_element:
            if self.active_element.is_visible() == False:
                return "Active element is currently not visible."

            try:
                self.active_element.focus()
                self.active_element.type(keys, delay=50)
                time.sleep(2)  
                return f"Keys sent to active element. Page Contents: {self.get_url_contents()}"
            except Exception as e:
                return f"Error sending keys to element: {str(e)}"
        return "Invalid active element. Set the active HTML element first."

    def highlight_active_element(self, highlight_color='black', duration=3000):
        """
        Creates a bounding box around the active element temporarily using Playwright's API.

        :param highlight_color: Color to use for the bounding box (default: black)
        :param duration: Duration in milliseconds for which the box should stay (default: 3000ms)
        """
        try:
            # Get the bounding box of the active element
            bounding_box = self.active_element.bounding_box()
            
            if bounding_box:
                # Create an object with all necessary data for the JavaScript to use
                box_data = {
                    'box': bounding_box,
                    'color': highlight_color,
                    'duration': duration
                }
                
                # Use Page.evaluate with a single argument (an object)
                self.page.evaluate('''
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
                print("Could not get bounding box for the active element.")
        except Exception as e:
            print(f"Error highlighting active element: {e}")

        return "Highlighted active element"

    def call_submit(self):
        """ Calls submit on the active element. """
        try:
            if self.active_element:
                # In Playwright, we can either press Enter or submit the form
                form = self.active_element.evaluate("el => el.closest('form')")
                if form:
                    self.active_element.evaluate("el => el.form.submit()")
                else:
                    self.active_element.press('Enter')
                return "Successfully called submit on active element"
            return "No active element to submit"
        except Exception as e:
            return f"Error submitting form: {str(e)}"

    def click_active_element(self):
        """ Clicks on the active element. """
        try:
            if self.active_element:
                try:
                    self.active_element.scroll_into_view_if_needed(timeout=2000)
                except:
                    pass
                self.active_element.click(force=True)
                time.sleep(2)
                return "Clicked element."
            return "Element is invalid. Ensure that a correct HTML element is selected."
        except Exception as e:
            error_message = f"Error clicking element: {str(e)}"
            print(error_message)
            print("Stack trace:", traceback.format_exc())
            return error_message

    def summarize(self, json_str: str):

        """Summarize the given json (html). (Mostly to save tokens)"""

        prompt = """You are a helpful assistant designed to extract relevant json data from a webpage HTML.
1. Extract the relevant elements from the json as concisely as possible. Do not print any other text.
2. Include all the attributes for the elements. This includes ids, classes, links and other tags.
3. Extract important text.
4. You will also be provided with the snapshot of the webpage. Use this information to summarize the data."""
        messages = MessageHistory(prompt)
        self.page.screenshot(path='browser.jpeg', type="jpeg", full_page=False, quality=50)
        if self.api != "ollama":
            messages.add_user_with_image(json_str, "browser.jpeg")
        else:
            messages.add_user_text(json_str)
        # messages.add_user_text(json_str)
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=messages.get_messages_for_api(),
        )
        print(f"Summary:{response.choices[0].message.content}")
        return response.choices[0].message.content

    def run(self):
        """Main Worker Loop"""
        tool_dict = {
            "move_to_url": self.move_to_url,
            "get_url_contents": self.get_url_contents,
            "set_active_element": self.set_active_element,
            "send_keys_to_active_element": self.send_keys_to_active_element,
            "call_submit": self.call_submit,
            "click_active_element": self.click_active_element,
            "highlight_active_element": self.highlight_active_element,
        }
        
        api_key = os.environ.get('XAI_API_KEY')
        if api_key is None and self.api == "xai":
            print("XAI_API_KEY environment variable not set.")
            sys.exit(1)

        if self.api == "openai":
            self.client = OpenAI()
        elif self.api == "xai":
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )
        elif self.api == "ollama":
            self.client = OpenAI(
                api_key="____",
                base_url='http://localhost:11434/v1'
            )
            
        last_time = time.time()

        try:
            while True:
                curr_time = time.time()

                if self.done:
                    user_input = input("Enter:")
                    self.done = False
                    # print(f"System: {user_input}")

                    self.messages.add_user_text(user_input)
                # else:
                #     # self.messages.add_user_text("Okay, keep going.")
                #     self.page.screenshot(path='browser.jpeg',type="jpeg", full_page=False)
                #     self.messages.add_user_with_image("Browser snapshot", "browser.jpeg")
                    # if get_page_elements(self.page) == self.prev_state:
                    #     pass
                    # else:
                    #     self.messages.add_user_text(self.get_url_contents())

                # print(self.messages.get_messages_for_api())

                response = self.client.chat.completions.create(
                    model=self.MODEL,
                    messages=self.messages.get_messages_for_api(),
                    tools=functions,
                    tool_choice="auto",
                    parallel_tool_calls=False
                )
                
                print(response)
                print(response.choices[0].message.content)
                
                if response.choices[0].message.content and len(response.choices[0].message.content.strip()) > 0:
                    self.messages.add_assistant_text(response.choices[0].message.content)

                if response.choices[0].message.tool_calls:
                    for tool_call in response.choices[0].message.tool_calls:
                        function_name = tool_call.function.name
                        print(f"Call: {function_name}")
                        function_args = json.loads(tool_call.function.arguments)

                        result = tool_dict[function_name](**function_args)
                        print(f"Result: {result}")

                        self.messages.add_tool_call(tool_call.id, function_name, tool_call.function.arguments)
                        self.messages.add_tool_response(tool_call.id, result, function_name) 
                        break
                else:
                    self.done = True

                last_time = curr_time
                curr_time = time.time()
                elapsed_time = curr_time - last_time
                print(f"Elapsed: {elapsed_time:.2f}s")
                
                if user_input.lower() == 'quit':
                    break
            
                # self.messages.trim_history(max_messages=self.MAX_MESSAGES)

        finally:
            # Clean up Playwright resources
            self.context.close()
            self.browser.close()
            self.playwright.stop()