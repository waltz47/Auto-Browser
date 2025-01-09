import json
from playwright.sync_api import Page, Locator
from typing import Dict, Any
import time

def enhance_json_with_selectors(page, json_string: str) -> Dict[str, Any]:
    """
    Parse JSON string and enhance it with robust XPath selectors.
    Priority is given to id, href, ariaLabel, and text. Falls back to combining all attributes if needed.
    Adds a count of elements found for each XPath.
    """
    try:
        # Parse JSON string
        data = json.loads(json_string)['elements']
        
        # List of supported attributes for building XPath
        supported_attributes = ["type", "placeholder", "role", "text", "id", "name", "href", "value"]

        def escape_xpath_string(value: str) -> str:
            """
            Escapes a string for use in XPath by using concat() for single quotes.
            """
            if "'" in value:
                parts = value.split("'")
                return "concat(" + ", ".join(f"'{part}'" for part in parts if part) + ", \"'\")"
            return f"'{value}'"
        
        # Process elements
        for element_type in ['inputs', 'buttons', 'links']:
            for elem in data.get(element_type, []):
                base_xpath = f"//{elem.get('tag', 'div')}"

                # Check for ID first
                if 'id' in elem and elem['id']:
                    base_xpath += f"[@id={escape_xpath_string(elem['id'])}]"
                # Then check for href if it's a link
                elif 'href' in elem and elem['href'] and elem.get('tag') == 'a':
                    base_xpath += f"[@href={escape_xpath_string(elem['href'])}]"
                # Check for aria-label
                elif 'ariaLabel' in elem and elem['ariaLabel']:
                    base_xpath += f"[@aria-label={escape_xpath_string(elem['ariaLabel'])}]"
                # Check for text using contains()
                elif 'text' in elem and elem['text']:
                    text = elem['text'].replace('\n', ' ').strip()
                    base_xpath += f"[contains(., {escape_xpath_string(text)})]"
                else:
                    # If none of the above work, combine all tags
                    conditions = []
                    for attr, value in elem.items():
                        if attr in supported_attributes and value:  # Ensure the attribute is supported and not empty
                            if attr == "ariaLabel":
                                conditions.append(f"@aria-label={escape_xpath_string(value)}")
                            elif attr == "text":
                                text = value.replace('\n', ' ').strip()
                                conditions.append(f"contains(., {escape_xpath_string(text)})")
                            else:
                                conditions.append(f"@{attr}={escape_xpath_string(value)}")
                    if conditions:
                        base_xpath += f"[{' and '.join(conditions)}]"

                elem['xpath_selector'] = base_xpath

                # Add count logic to handle multiple elements
                try:
                    elements = page.query_selector_all(f"xpath={base_xpath}")
                    # elem['element_count'] = len(elements)
                except Exception as e:
                    # elem['element_count'] = 0
                    elem['error'] = str(e)

        return data

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON string: {str(e)}")

def test_selectors_on_page(page: Page, enhanced_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test the XPath selectors on the given page and add results to the JSON.
    """
    # Process inputs
    for input_elem in enhanced_json.get('inputs', []):
        try:
            element = page.wait_for_selector(f"xpath={input_elem['xpath_selector']}", 
                                           timeout=100, state="attached")
            input_elem['test_result'] = {
                'found': bool(element),
                'visible': element.is_visible() if element else False,
                'status': 'success'
            }
        except Exception as e:
            input_elem['test_result'] = {
                'found': False,
                'error': str(e),
                'status': 'error'
            }
    
    # Process buttons
    for button in enhanced_json.get('buttons', []):
        try:
            element = page.wait_for_selector(f"xpath={button['xpath_selector']}", 
                                           timeout=100, state="attached")
            button['test_result'] = {
                'found': bool(element),
                'visible': element.is_visible() if element else False,
                'status': 'success'
            }
        except Exception as e:
            button['test_result'] = {
                'found': False,
                'error': str(e),
                'status': 'error'
            }
    
    # Process links
    for link in enhanced_json.get('links', []):
        try:
            element = page.wait_for_selector(f"xpath={link['xpath_selector']}", 
                                           timeout=100, state="attached")
            link['test_result'] = {
                'found': bool(element),
                'visible': element.is_visible() if element else False,
                'status': 'success'
            }
        except Exception as e:
            link['test_result'] = {
                'found': False,
                'error': str(e),
                'status': 'error'
            }
    
    return enhanced_json


def process(worker, json_string):
    time_start = time.time()
    print(json_string)
    enhanced_json = enhance_json_with_selectors(worker.page, json_string)
    results = test_selectors_on_page(worker.page, enhanced_json)

    print(f"time (enhance): {time.time() - time_start}")
    time_start = time.time()

    tags = ["inputs", "buttons", "links"]

    for tag in tags:
        for input_elem in results.get(tag, []):
            if input_elem['test_result']['status'] != 'success':
                continue
            selector = f"{input_elem['xpath_selector']}"
            worker.highlight_element(selector, "grey", 2000)
            # time.sleep(0.0)

    for tag in tags:
        for input_elem in results.get(tag, []):
            del input_elem['test_result']

    print(f"time (summarize): {time.time() - time_start}")

    open("log/cleaned.log", "w", encoding="utf-8").write(str(json.dumps(results,indent=2)))
    return str(json.dumps(results,indent=2))

# Example usage:
"""
# First enhance the JSON with selectors
json_string = '''
{
    "inputs": [...],
    "buttons": [...],
    "links": [...]
}
'''

enhanced_json = enhance_json_with_selectors(json_string)

# Then test the selectors on an already open page
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    # Assuming page is already navigated to the target URL
    results = test_selectors_on_page(page, enhanced_json)
    
    # Print or process results
    print(json.dumps(results, indent=2))
"""