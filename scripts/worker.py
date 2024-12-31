import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException
import time
import metrics
from metrics import *
from defs import *
from openai import OpenAI
import json
import base64
import sys
import traceback

"""
Worked class designed to perform web actions via tools.
"""

class Worker:
    def __init__(self):
        self.driver = None
        self.active_element = None 
        self.done = True
        self.messages = [
            {'role':'system','content':'''You are a helpful assistant designed to perform web actions via tools.

Here are the tools provided to you:
- move_to_url: Set a specific url as the active page.
- get_url_contents: Get the contents from the active page. Required when a new url is opened or changes are made to the page.
- set_active_element: Set a HTML page element as active (class names can be one of the following: 'id','class','name','tag','link','partial_link','xpath','css').
- send_keys_to_active_element: Send keys to page HTML element (for eg. to input text).
- submit: Submit the active HTML element (for eg. to submit a form).
- click_active_element: Click active HTML element.

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
    - Read the contents and output the answer to the question.'''}
]

        self.driver_options = Options()
        # if  os.environ.get('FIREFOX_PROFILE'):
        #     self.driver_options.profile = os.environ.get('FIREFOX_PROFILE')
        #     if not os.path.exists(os.environ.get('FIREFOX_PROFILE')):
        #         print(f"The profile path {os.environ.get('FIREFOX_PROFILE')} does not exist.")
        #     else:
        #         print("Profile path exists.")
        # self.driver_options.add_argument("--headless")  # Run in headless mode for automation
        self.driver = webdriver.Firefox(options=self.driver_options)

    def move_to_url(self, url):
        try:
            self.driver.get(url)
        except:
            return "Url Invalid."
        # self.driver.implicitly_wait(5)
        time.sleep(5)

        return f"Current page set to {url}. Use get_url_contents to get the contents of the page."

    def get_url_contents(self):
        self.active_element = None
        try:
            time_a = time.time()
            elements = self.driver.find_elements(By.XPATH, "//*")
            print(f"Time to get elements: {time.time() - time_a:.2f}s")
            element_info = []
            element_tags = []
            ignored_tags = set(["script", "span",'hr', 'center', 'svg', 'rect', 'style', 'meta', 'link', 'path', 'img', 'div', 'picture', 'image'])
            time_b = time.time()
            for element in elements:
                try:
                    if element.tag_name in ignored_tags:
                        continue
                    
                    if element.tag_name not in element_tags:
                        element_tags.append(element.tag_name)
                    info = {
                        "tag_name": element.tag_name,
                        "text": element.text if element.text else "No Text",
                        "attributes": {},
                        # "is_interactable": element.is_enabled()
                    }
                    for attr in ['id', 'class', 'href', 'src', 'title', 'alt', 'name']:
                        value = element.get_attribute(attr)
                        if value:
                            info["attributes"][attr] = value
                    if len(info["attributes"]) == 0 and info['text'] == "No Text":
                        continue
                    element_info.append(info)
                except Exception as e:
                    print(f"Error processing element: {e}")
            print(f"Time to process elements: {time.time() - time_b:.2f}s")
        except Exception as e:
            print(f"An error occurred during GET: {e}")
        print("Element tags:", element_tags)
        return "*****HTML ELEMENTS**********\n\n" + str(element_info) + "\n\n ***********END OF HTML ELEMENTS*****"

    def find_element_by(self, locator_type, locator_value, input_type=None):
        strategies = {
            'id': By.ID,
            'class': By.CLASS_NAME,
            'name': By.NAME,
            'tag': By.TAG_NAME,
            'link': By.LINK_TEXT,
            'partial_link': By.PARTIAL_LINK_TEXT,
            'xpath': By.XPATH,
            'css': By.CSS_SELECTOR
        }
        
        if locator_type.lower() in strategies:
            try:
                element = self.driver.find_element(strategies[locator_type.lower()], locator_value)
                if input_type and element.tag_name == 'input':
                    if element.get_attribute('type') != input_type:
                        raise NoSuchElementException(f"Element found but type '{element.get_attribute('type')}' does not match '{input_type}'")
                return element
            except:
                print("Element not found.")
                return None
        else:
            raise ValueError(f"Unsupported locator type: {locator_type}. Available types are: {', '.join(strategies.keys())}")

    def set_active_element(self, type_name: str, class_name: str):
        print(f"Getting element with type: {type_name} and class: {class_name}")
        try:
            self.active_element = self.find_element_by(type_name, class_name)
            if self.active_element is None:
                return "Element not found. Invalid type_name/class_name/both. Recheck the arguments."
        except:
            return "Class element not found."
        return f"Active element updated to element of class: {class_name}"

    def send_keys_to_active_element(self, keys: str):
        if self.active_element:
            self.active_element.send_keys(keys)
            # self.active_element.submit()
            return "Keys sent to active element"
        return "Invalid active element. Set the active HTML element first."

    def call_submit(self):
        try:
            self.active_element.submit()
            return "Successfully called submit on active element"
        except:
            return f"Error occurred while calling submit() on active element: {str(self.active_element)}"

    def click_active_element(self):
        try:
            # Scroll the element into view using JavaScript
            self.driver.execute_script("arguments[0].scrollIntoView(true);", self.active_element)
            self.active_element.click()
            return "Successfully called click on active element"
        except Exception as e:
            error_message = f"Error occurred while calling click() on active element: {str(self.active_element)}"
            print(error_message)
            print("Exception message:", str(e))
            print("Stack trace:", traceback.format_exc())
            return error_message

    def on_task_completion(self):
        self.done = True
        return "Task completed"

    #Main Loop
    def run(self):
        tool_dict = {
            "move_to_url": self.move_to_url,
            "get_url_contents": self.get_url_contents,
            "set_active_element" : self.set_active_element,
            "send_keys_to_active_element" : self.send_keys_to_active_element,
            "call_submit" : self.call_submit,
            "click_active_element" : self.click_active_element,
        }
        api_key = os.environ.get('XAI_API_KEY')
        # print("API:", api_key)

        if api_key is None:
            print("XAI_API_KEY environment variable not set.")
            sys.exit(1)
        if self.api == "openai":
            client = OpenAI()
        else:
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )

        last_time = time.time()

        while True:
            curr_time = time.time()

            # print(self.messages)

            #handle user input, if required
            if self.done:
                user_input = input("Enter:")
                # Note: self.messages is passed by reference to get_system_dir
                # user_input = self.owner.get_system_dir(self.messages)

                self.done = False

                print(f"System: {user_input}")
                print(f"Num tokens (approx.): {avg_tokens(user_input)}")

                if self.VISION == False:
                    self.messages.append({'role':'user', 'content': user_input})
                else:
                    self.driver.save_screenshot("browser.png")
                    with open("browser.png", "rb") as image_file:
                        encoded = base64.b64encode(image_file.read()).decode('utf-8')
                    self.messages.append({
                        'role': 'user', 
                        'content': [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "high"}},
                            {"type": "text", "text": user_input}
                        ]
                    })
            else:
                if self.VISION:
                    self.driver.save_screenshot("browser.png")
                    with open("browser.png", "rb") as image_file:
                        encoded = base64.b64encode(image_file.read()).decode('utf-8')
                    self.messages.append({
                        'role': 'user', 
                        'content': [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "high"}},
                            {"type": "text", "text": "Browser window screenshot for context."}
                        ]
                    })
                print("Continuing...")
                self.messages.append({'role':'user', 'content': "Okay, keep going."})

            # Keep only the last MAX_MESSAGES number of conversations, including the system prompt
            if len(self.messages) > self.MAX_MESSAGES + 2:
                self.messages = [self.messages[0]] + [self.messages[1]] + self.messages[-self.MAX_MESSAGES:]

            # Iterate in reverse to find and replace old HTML content tool calls
            found_html_content = False
            for i in range(len(self.messages) - 1, -1, -1):
                if 'HTML ELEMENTS' in self.messages[i].get('content', ''):
                    if found_html_content:
                        self.messages[i]['content'] = '***HTML ELEMENTS (OLD)***'
                    else:
                        found_html_content = True
            # print(self.messages)
            response = client.chat.completions.create(
                model=self.MODEL,
                messages=self.messages,
                tools=functions,
                tool_choice="auto"                
            )
            print(response)
            print(response.choices[0].message.content)
            if response.choices[0].message.content and len(response.choices[0].message.content.strip()) > 0:
                self.messages.append({'role':'assistant', 'content': response.choices[0].message.content})

            if response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    # Get the tool function name and arguments Grok wants to call
                    function_name = tool_call.function.name
                    print(f"Function call: {function_name}")
                    function_args = json.loads(tool_call.function.arguments)

                    if self.api == "openai":
                        self.messages.append(
                            {
                                'role': 'assistant', 
                                'tool_calls': [{'id': tool_call.id, 'function': {'arguments': tool_call.function.arguments, 'name': function_name}, 'type':'function'}]
                            }
                        )

                    # Call one of the tool function defined earlier with arguments
                    result = tool_dict[function_name](**function_args)
                    print(f"Result: {result}")

                    # Append the result from tool function call to the chat message history,
                    # with "role": "tool" to indicate that it is a tool response
                    self.messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(result),
                            "tool_call_id": tool_call.id  # tool_call.id supplied in Grok's response
                        }
                    )
            else:
                self.done = True

            last_time = curr_time
            curr_time = time.time()
            elapsed_time = curr_time - last_time
            print(f"Elapsed: {elapsed_time:.2f}s")
            if user_input.lower() == 'quit':
                break

        self.driver.quit()
