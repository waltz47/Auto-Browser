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
import grok
from openai import OpenAI
import json
import base64
import sys
import traceback

class Nyx:
    # MODEL="qwen2.5-coder:7b-instruct-q4_0"
    MODEL='grok-2-latest'
    # MODEL = "grok-2-vision-1212"
    VISION=False #for grok-2-vision

    def __init__(self):
        self.driver = None
        self.active_element = None 
        self.done = True
        self.messages = [
            {'role':'system','content':'''You are a helpful assistant designed to perform web actions via tools. Perform the following steps:
                - Open the relevant webpage.
                - Get the relevent element (input text or link)
                - Enter data.
                - Click or submit.

            Here are the tools provided to you:
                - move_to_url: Set a specific url as the active page.
                - get_url_contents: Get the contents from the active page.
                - set_active_element: Set a page element as active (class names can be one of the following: 'id','class','name','tag','link','partial_link','xpath','css').
                - send_keys_to_active_element: Send keys to page element (for eg. to input text).
                - call_submit: Call submit on active element.
                - click_active_element: Click active element.
                - on_task_completion: Required to call when user input is required.
            
            Make multiple function calls in a single message to perform multiple actions.
            '''}
        ]

        self.driver_options = Options()
        # self.driver_options.add_argument("--headless")  # Run in headless mode for automation
        self.driver = webdriver.Firefox(options=self.driver_options)

    def move_to_url(self, url):
        try:
            self.driver.get(url)
        except:
            return "Url Invalid."
        WebDriverWait(self.driver, 3)
        return f"Current page set to {url}"

    def get_url_contents(self):
        try:
            elements = self.driver.find_elements(By.XPATH, "//*")
            element_info = []
            element_tags = []
            ignored_tags = ["script", "span",'hr', 'center', 'svg', 'rect', 'style', 'meta', 'link', 'path', 'img', 'div']
            for element in elements:
                try:
                    if element.tag_name in ignored_tags:
                        continue
                    
                    if element.tag_name not in element_tags:
                        element_tags.append(element.tag_name)
                    info = {
                        "tag_name": element.tag_name,
                        "text": element.text.strip() if element.text else "No Text",
                        "attributes": {},
                        # "is_interactable": element.is_enabled()
                    }
                    for attr in ['id', 'class', 'href', 'src', 'title', 'alt', 'name']:
                        value = element.get_attribute(attr)
                        if value:
                            info["attributes"][attr] = value
                    element_info.append(info)
                except Exception as e:
                    print(f"Error processing element: {e}")

        except Exception as e:
            print(f"An error occurred during GET: {e}")
        print("Element tags:", element_tags)
        return str(element_info)

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
        try:
            self.active_element = self.find_element_by(type_name, class_name)
            if self.active_element is None:
                return "Element not found"
        except:
            return "Class element not found."
        return f"Active element updated to element of class: {class_name}"

    def send_keys_to_active_element(self, keys: str):
        if self.active_element:
            self.active_element.send_keys(keys)
            return "Keys sent"
        return "Invalid active element"

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

    #Main Loop
    def run(self):
        tool_dict = {
            "move_to_url": self.move_to_url,
            "get_url_contents": self.get_url_contents,
            "set_active_element" : self.set_active_element,
            "send_keys_to_active_element" : self.send_keys_to_active_element,
            "call_submit" : self.call_submit,
            "click_active_element" : self.click_active_element,
            "on_task_completion": self.on_task_completion,
        }
        api_key = os.environ.get('XAI_API_KEY')
        print("API:", api_key)

        if api_key is None:
            print("XAI_API_KEY environment variable not set.")
            sys.exit(1)

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )

        last_time = time.time()

        while True:
            curr_time = time.time()

            #handle user input, if required
            if self.done:
                user_input = input("Enter:")
                self.done = False

                print(f"User Input: {user_input}")
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
                print("Continuing...")

            # print(self.messages)
            response = client.chat.completions.create(
                model=self.MODEL,
                messages=self.messages,
                tools=functions,
                tool_choice="auto",
            )
            print(response)
            print(response.choices[0].message.content)
            if len(response.choices[0].message.content.strip()) > 0:
                self.messages.append({'role':'assistant', 'content': response.choices[0].message.content})

            if response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    # Get the tool function name and arguments Grok wants to call
                    function_name = tool_call.function.name
                    print(f"Function call: {function_name}")
                    function_args = json.loads(tool_call.function.arguments)

                    # Call one of the tool function defined earlier with arguments
                    result = tool_dict[function_name](**function_args)
                    print(f"Result: {result}")

                    # Append the result from tool function call to the chat message history,
                    # with "role": "tool"
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

if __name__ == "__main__":
    nyx = Nyx()
    nyx.run()