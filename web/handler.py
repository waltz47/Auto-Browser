import json
from playwright.async_api import Page, Locator  # Changed to async_api
from typing import Dict, Any
import time

async def enhance_json_with_selectors(page: Page, json_string: str) -> Dict[str, Any]:
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
        for element_type in ['inputs', 'buttons', 'links', "apps", "nav"]:
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
                    elements = await page.query_selector_all(f"xpath={base_xpath}")  # Now awaited
                    # elem['element_count'] = len(elements)
                except Exception as e:
                    # elem['element_count'] = 0
                    elem['error'] = str(e)

        return data

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON string: {str(e)}")

async def test_selectors_on_page(page: Page, enhanced_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test the XPath selectors on the given page and add results to the JSON.
    """
    # Process inputs
    for input_elem in enhanced_json.get('inputs', []):
        try:
            element = await page.wait_for_selector(f"xpath={input_elem['xpath_selector']}", 
                                                  timeout=10, state="attached")  # Now awaited
            input_elem['test_result'] = {
                'found': bool(element),
                'visible': await element.is_visible() if element else False,  # Now awaited
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
            element = await page.wait_for_selector(f"xpath={button['xpath_selector']}", 
                                                  timeout=10, state="attached")  # Now awaited
            button['test_result'] = {
                'found': bool(element),
                'visible': await element.is_visible() if element else False,  # Now awaited
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
            element = await page.wait_for_selector(f"xpath={link['xpath_selector']}", 
                                                  timeout=10, state="attached")  # Now awaited
            link['test_result'] = {
                'found': bool(element),
                'visible': await element.is_visible() if element else False,  # Now awaited
                'status': 'success'
            }
        except Exception as e:
            link['test_result'] = {
                'found': False,
                'error': str(e),
                'status': 'error'
            }
    
    return enhanced_json

async def process(worker, json_string):
    time_start = time.time()
    enhanced_json = await enhance_json_with_selectors(worker.page, json_string)  # Now awaited
    results = await test_selectors_on_page(worker.page, enhanced_json)  # Now awaited

    print(f"time (enhance): {time.time() - time_start}")
    time_start = time.time()

    tags = ["inputs", "buttons", "links", "apps", "nav"]

    for tag in tags:
        for input_elem in results.get(tag, []):
            selector = f"{input_elem['xpath_selector']}"
            try:
                if input_elem['test_result']['status'] != 'success':
                    continue
            
                # await worker.highlight_element(selector, "red", 2000, True)  # Uncomment and await if needed
            except:
                print(f"NA XPath: {selector}")
            
            if tag == "links":
                try:
                    del input_elem['href']
                except:
                    pass
    try:
        for tag in tags:
            for input_elem in results.get(tag, []):
                del input_elem['test_result']
    except:
        pass

    print(f"time (summarize): {time.time() - time_start}")

    results["elements_by_type"] = json.loads(json_string)['elements_by_type']
    open(f"log/cleaned_{worker.worker_id}.log", "w", encoding="utf-8").write(str(json.dumps(results, indent=2)))
    return str(json.dumps(results, indent=2))

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

import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        # Assuming page is already navigated to the target URL
        enhanced_json = await enhance_json_with_selectors(page, json_string)
        results = await test_selectors_on_page(page, enhanced_json)
        
        # Print or process results
        print(json.dumps(results, indent=2))
        await browser.close()

asyncio.run(main())
"""