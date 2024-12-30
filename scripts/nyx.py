import os
import ollama
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import time

streaming=False

messages = [{'role':'system','content':'''You are a helpful assistant. You will be given selenium output json containing elements of a webpage. You need to find the correct element and perform the action required by the user.  Some examples might be: entering text, clicking button, clicking on a link.
When interacting with elements, follow this given steps:
    - Find the relevant element and set it as the active element
    - Perform action on the active element
    - Submit/Click if required.
    
Give the reasoning behind your actions/output.

Here are the tools provided to you:
    - set_active_element (class names can be one of the following: 'id','class','name','tag','link','partial_link','xpath','css')
    - send_keys_to_active_element
    - call_submit
    - click_active_element
'''}]

driver_options = Options()
# driver_options.add_argument("--headless")  # Run in headless mode for automation
# service = Service(executable_path='/path/to/chromedriver')  # Replace with your chromedriver path
driver = webdriver.Firefox(options=driver_options)
active_element = None
def driver_get() -> str:
    driver.get("https://www.google.com")
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "q")))
        
        # elements = driver.find_elements(By.XPATH, "//div | //a | //span | //p | //input | //button | //select | //textarea")
        elements = driver.find_elements(By.XPATH, "//*")
        
        element_info = []
        element_tags = []
        ignored_tags = ["script", "span"]
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
                    "is_interactable": element.is_enabled()
                }
                # Collect only attributes that exist
                for attr in ['id', 'class', 'href', 'src', 'title', 'alt', 'name']:
                    value = element.get_attribute(attr)
                    if value:
                        info["attributes"][attr] = value
                element_info.append(info)
            except Exception as e:
                print(f"Error processing element: {e}")

    except Exception as e:
        print(f"An error occurred during waiting or interaction: {e}")
    print("Element tags:", element_tags)
    return str(element_info)

def find_element_by(driver, locator_type, locator_value, input_type=None):
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
            element = driver.find_element(strategies[locator_type.lower()], locator_value)
            if input_type and element.tag_name == 'input':
                if element.get_attribute('type') != input_type:
                    raise NoSuchElementException(f"Element found but type '{element.get_attribute('type')}' does not match '{input_type}'")
            return element
        except:
            print("fffffffffffffff")
    else:
        raise ValueError(f"Unsupported locator type: {locator_type}. Available types are: {', '.join(strategies.keys())}")

def set_active_element(type_name: str, class_name: str):
    try:
        global active_element
        active_element = find_element_by(driver, type_name, class_name)
    except:
        return "Class element not found."
    return f"Active element updated to element of class: {class_name}"

def send_keys_to_active_element(keys: str):
    global active_element
    if active_element:
        active_element.send_keys(keys)
    else:
        return "Invalid active element"
    return "Keys sent"

def call_submit():
    try:
        active_element.submit()
    except:
        return f"Error occured while calling submit() on active element: {str(active_element)}" 
    return "Successfully called submit on active element"
def click_active_element():
    try:
        active_element.click()
    except:
        return f"Error occured while calling click() on active element: {str(active_element)}" 
    return "Successfully called click on active element"

tools = [set_active_element, send_keys_to_active_element, call_submit, click_active_element]
tool_dict = {
    "set_active_element" : set_active_element,
    "send_keys_to_active_element" : send_keys_to_active_element,
    "call_submit" : call_submit,
    "click_active_element" : click_active_element,
}

driver_output = driver_get()
first = True
while True:
    
    user_input = input("Enter:")
    if first:
        user_input = user_input + '\n\nELEMENTS:\n' + driver_output
        first = False

    print (f"User Input: {user_input}")
    messages.append({'role':'user', 'content': user_input})

    response = ollama.chat(model="qwen2.5-coder:3b", options={"temperature":0.0, "top_p":0.95,"num_ctx":24000, "num_threads":6},messages=messages,tools=tools, stream=streaming)

    if streaming == False:
        print(response.message.content)
        messages.append({'role':'assistant', 'content': response.message.content})
    else:
        assistant_response = ''
        for chunk in response:
            print(chunk['message']['content'],end='',flush=True)
            assistant_response += chunk['message']['content']
        messages.append({'role':'assistant', 'content': assistant_response})

    if response.message.tool_calls:
        for tool in response.message.tool_calls:
            if function_to_call := tool_dict.get(tool.function.name):
                print('Calling function:', tool.function.name)
                print('Arguments:', tool.function.arguments)
                output = function_to_call(**tool.function.arguments)
                print('Function output:', output)
                messages.append({'role': 'tool', 'content': str(output), 'name': tool.function.name})
            else:
                print('Function', tool.function.name, 'not found')
            break #allowing only one call 

driver.quit()