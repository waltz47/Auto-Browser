import json
from playwright.async_api import Page, Locator
from typing import Dict, Any, List
import time
from .profiler import Timer, async_profile
import asyncio

async def enhance_json_with_selectors(page: Page, json_string: str) -> Dict[str, Any]:
    """
    Parse JSON string and enhance it with robust XPath selectors.
    Priority is given to id, href, ariaLabel, and text. Falls back to combining all attributes if needed.
    Adds a count of elements found for each XPath.
    """
    try:
        async with Timer("JSON parsing"):
            data = json.loads(json_string)['elements']
        
        supported_attributes = ["type", "placeholder", "role", "text", "id", "name", "href", "value"]

        def escape_xpath_string(value: str) -> str:
            """
            Escapes a string for use in XPath by using concat() for single quotes.
            """
            if "'" in value:
                parts = value.split("'")
                return "concat(" + ", ".join(f"'{part}'" for part in parts if part) + ", \"'\")"
            return f"'{value}'"
        
        async def process_element(elem: Dict[str, Any]) -> Dict[str, Any]:
            base_xpath = f"//{elem.get('tag', 'div')}"

            # Build XPath with priority order
            if 'id' in elem and elem['id']:
                base_xpath += f"[@id={escape_xpath_string(elem['id'])}]"
            elif 'href' in elem and elem['href'] and elem.get('tag') == 'a':
                base_xpath += f"[@href={escape_xpath_string(elem['href'])}]"
            elif 'ariaLabel' in elem and elem['ariaLabel']:
                base_xpath += f"[@aria-label={escape_xpath_string(elem['ariaLabel'])}]"
            elif 'text' in elem and elem['text']:
                text = elem['text'].replace('\n', ' ').strip()
                base_xpath += f"[contains(., {escape_xpath_string(text)})]"
            else:
                conditions = [
                    f"@{attr}={escape_xpath_string(value)}" if attr != "text" else f"contains(., {escape_xpath_string(value)})"
                    for attr, value in elem.items()
                    if attr in supported_attributes and value
                ]
                if conditions:
                    base_xpath += f"[{' and '.join(conditions)}]"

            elem['xpath_selector'] = base_xpath
            return elem

        # Process all elements concurrently in batches
        async with Timer("Process elements"):
            for element_type in ['inputs', 'buttons', 'links', "apps", "nav"]:
                elements = data.get(element_type, [])
                if not elements:
                    continue

                # Process in batches of 10 to avoid overwhelming the browser
                batch_size = 10
                for i in range(0, len(elements), batch_size):
                    batch = elements[i:i + batch_size]
                    processed = await asyncio.gather(*[process_element(elem) for elem in batch])
                    
                    # Validate selectors in batch
                    selector_tasks = [
                        page.query_selector_all(f"xpath={elem['xpath_selector']}")
                        for elem in processed
                    ]
                    try:
                        await asyncio.gather(*selector_tasks)
                    except Exception as e:
                        print(f"Error validating selectors: {str(e)}")
                    
                    # Update the original list
                    for j, elem in enumerate(processed):
                        elements[i + j] = elem

        return data

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON string: {str(e)}")

@async_profile
async def test_selectors_on_page(page: Page, enhanced_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test the XPath selectors on the given page and add results to the JSON.
    """
    async def bulk_check_elements(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Create a JavaScript function to check multiple elements at once
        js_check_elements = """
        (selectors) => {
            return selectors.map(selector => {
                try {
                    const elements = document.evaluate(selector, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    return {
                        found: elements.snapshotLength > 0,
                        count: elements.snapshotLength
                    };
                } catch (e) {
                    return { found: false, error: e.toString() };
                }
            });
        }
        """
        
        # Extract just the XPath selectors
        selectors = [elem['xpath_selector'].replace('xpath=', '') for elem in elements]
        
        # Run the bulk check
        try:
            results = await page.evaluate(js_check_elements, selectors)
            
            # Update elements with results
            for elem, result in zip(elements, results):
                if result.get('found', False):
                    # Element exists, now just check visibility
                    try:
                        element = await page.query_selector(f"xpath={elem['xpath_selector']}")
                        is_visible = await element.is_visible() if element else False
                        elem['test_result'] = {
                            'found': True,
                            'visible': is_visible,
                            'status': 'success'
                        }
                    except:
                        elem['test_result'] = {
                            'found': True,
                            'visible': False,
                            'status': 'success'
                        }
                else:
                    elem['test_result'] = {
                        'found': False,
                        'error': result.get('error', 'Element not found'),
                        'status': 'error'
                    }
        except Exception as e:
            # If bulk operation fails, fall back to individual checks
            print(f"Bulk check failed: {str(e)}, falling back to individual checks")
            return await fallback_check_elements(elements)
            
        return elements

    async def fallback_check_elements(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        async def check_single_element(elem: Dict[str, Any]) -> Dict[str, Any]:
            try:
                # Quick check first
                element = await page.query_selector(f"xpath={elem['xpath_selector']}")
                if element:
                    elem['test_result'] = {
                        'found': True,
                        'visible': await element.is_visible(),
                        'status': 'success'
                    }
                else:
                    # Short timeout for waiting
                    element = await page.wait_for_selector(
                        f"xpath={elem['xpath_selector']}", 
                        timeout=100,  # 0.1 second timeout
                        state="attached"
                    )
                    elem['test_result'] = {
                        'found': bool(element),
                        'visible': await element.is_visible() if element else False,
                        'status': 'success'
                    }
            except Exception as e:
                elem['test_result'] = {
                    'found': False,
                    'error': str(e),
                    'status': 'error'
                }
            return elem

        # Process elements concurrently
        return await asyncio.gather(*[check_single_element(elem) for elem in elements])

    # Process in larger batches since we're doing bulk operations
    batch_size = 25
    
    for element_type in ['inputs', 'buttons', 'links']:
        elements = enhanced_json.get(element_type, [])
        if not elements:
            continue
            
        async with Timer(f"Processing {element_type}"):
            for i in range(0, len(elements), batch_size):
                batch = elements[i:i + batch_size]
                processed = await bulk_check_elements(batch)
                for j, elem in enumerate(processed):
                    elements[i + j] = elem
    
    return enhanced_json

@async_profile
async def process(worker, json_string):
    async with Timer("Total process time"):
        async with Timer("Enhance JSON"):
            enhanced_json = await enhance_json_with_selectors(worker.page, json_string)
        
        async with Timer("Test selectors"):
            results = await test_selectors_on_page(worker.page, enhanced_json)

        async with Timer("Process results"):
            tags = ["inputs", "buttons", "links", "apps", "nav"]

            for tag in tags:
                for input_elem in results.get(tag, []):
                    selector = f"{input_elem['xpath_selector']}"
                    try:
                        if input_elem['test_result']['status'] != 'success':
                            continue
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

        async with Timer("Write results"):
            results["elements_by_type"] = json.loads(json_string)['elements_by_type']
            open(f"log/cleaned_{worker.worker_id}.log", "w", encoding="utf-8").write(str(json.dumps(results, indent=2)))
            return str(json.dumps(results, indent=2))
