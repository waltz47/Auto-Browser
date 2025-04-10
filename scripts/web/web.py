from typing import List, Dict, Any
from playwright.async_api import Page  # Changed to async_api
import time
import json
from .profiler import Timer, async_profile

@async_profile
async def get_page_elements(page: Page) -> str:
    """
    Get a clean, structured representation of important page elements.
    Returns elements in a format that's easy for LLMs to understand.
    """
    async with Timer("Total get_page_elements time"):
        async with Timer("Setup selectors"):
            # These elements are typically interactive or contain important content
            important_selectors = [
                "input", "button", "a[href]", "select", "textarea",
                "form", 
                "label",
                "table", "ul", "ol", "nav",
                "[role='button']", "[role='link']", "[role='menuitem']", "[role='tab']",
                "[onclick]", "[class*='button']", "[class*='btn']",
                "[type='search']", "[aria-label*='search' i]",
                "[class*='menu']", "[class*='nav']", "iframe",
                "span"
            ]

            react_selectors = [ "[data-reactroot]", 
                "[data-reactid]",   
                "[data-react-helmet]", 
                "[class*='React']", 
                "[class*='react-']", 
                'react-app[app-name="react-code-view"]',
                "[data-target='react-partial.embeddedData']"
            ]

            vue_selectors = ["[data-v-]",  
                "[v-if]",     
                "[v-for]",    
                "[v-bind]",   
                "[v-on]",     
                "[class*='vue']"
            ]
            
            combined_selector = ", ".join(important_selectors + react_selectors + vue_selectors)

        async with Timer("Query elements"):
            # Get elements matching our selectors
            elements = await page.query_selector_all(combined_selector)

        async with Timer("Process elements"):
            structured_elements: List[Dict[str, Any]] = []
            
            # JavaScript function as a single line with proper escaping
            js_element_info = """
                (element) => {
                    const rect = element.getBoundingClientRect();
                    const computedStyle = window.getComputedStyle(element);
                    return {
                        tag: element.tagName.toLowerCase(),
                        type: element.type || undefined,
                        id: element.id || undefined,
                        name: element.name || undefined,
                        value: element.value || undefined,
                        href: element.getAttribute('href') || undefined,
                        src: element.src || undefined,
                        placeholder: element.placeholder || undefined,
                        ariaLabel: element.getAttribute('aria-label') || undefined,
                        ariaDescribedby: element.getAttribute('aria-describedby') || undefined,
                        role: element.getAttribute('role') || undefined,
                        title: element.title || undefined,
                        text: (element.innerText || '').substring(0, 100),
                        isVisible: rect.width > 0 && rect.height > 0 && computedStyle.display !== 'none' && computedStyle.visibility !== 'hidden',
                        disabled: element.disabled || false,
                        checked: element.checked || undefined,
                        selected: element.selected || undefined,
                        multiple: element.multiple || undefined
                    };
                }
                """.replace('\n', ' ').strip()

            ignored_tags = []
            ignored_href_strings = ["policy", "policies", "facebook", "store", "googleadservices", "instagram"]
            MAX_LINKS = 40
            MAX_ELEMENTS = 100

            for element in elements:
                try:
                    # Get element info using the JavaScript function
                    element_info = await element.evaluate(js_element_info)
                    
                    # Clean up the element info by removing undefined values
                    element_info = {k: v for k, v in element_info.items() if k is not None and v is not None and v != "undefined"}
                    
                    # Skip empty or uninformative elements
                    if not any([
                        element_info.get('text'),
                        element_info.get('value'),
                        element_info.get('placeholder'),
                        element_info.get('ariaLabel')
                    ]):
                        continue
                        
                    # Skip hidden elements
                    if not element_info.get('isVisible', True):
                        continue

                    if element_info.get("tag") in ignored_tags:
                        continue

                    if element_info.get("tag") == "a":
                        if MAX_LINKS == 0:
                            continue
                        if element_info.get("href") == None:
                            continue
                        
                        ignored = False
                        for ignored_href in ignored_href_strings:
                            if ignored_href in element_info.get("href"):
                                ignored = True
                                break
                        if ignored:
                            continue
                        MAX_LINKS -= 1

                    element_info.pop("disabled", None)
                    element_info.pop("isVisible", None)
                    
                    structured_elements.append(element_info)

                    if len(structured_elements) > MAX_ELEMENTS:
                        break
                    
                except Exception as e:
                    print(f"Error processing element: {e}")
                    continue

        async with Timer("Group elements"):
            # Group elements by type
            grouped_elements = {
                "inputs": [],
                "buttons": [],
                "links": [],
                "headings": [],
                "navigation": [],
                "apps": [],
                "other": []
            }
            
            for element in structured_elements:
                tag = element.get('tag', '')
                role = element.get('role', '')
                
                if tag == 'input' or tag == 'textarea':
                    grouped_elements["inputs"].append(element)
                elif tag == 'button' or role == 'button':
                    grouped_elements["buttons"].append(element)
                elif tag == 'a' or role == 'link':
                    grouped_elements["links"].append(element)
                elif tag.startswith('h') and len(tag) == 2:
                    grouped_elements["headings"].append(element)
                elif tag == 'nav' or (element.get('classes', '').find('nav') != -1):
                    grouped_elements["navigation"].append(element)
                elif "react" in tag:
                    grouped_elements["apps"].append(element)
            
            # Remove empty categories
            grouped_elements = {k: v for k, v in grouped_elements.items() if v}
            
            # Create a summary
            summary = {
                "total_elements": len(structured_elements),
                "elements_by_type": {
                    category: len(elements)
                    for category, elements in grouped_elements.items()
                },
                "elements": grouped_elements
            }
            
            return json.dumps(summary, indent=2)

async def get_focused_element_info(page: Page) -> Dict[str, Any]:
    """
    Get information about the currently focused element.
    """
    async with Timer("Get focused element"):
        js_focused = """
        () => {
            const active = document.activeElement;
            if (!active) return null;
            return {
                tag: active.tagName.toLowerCase(),
                type: active.type || undefined,
                id: active.id || undefined,
                name: active.name || undefined,
                value: active.value || undefined,
                placeholder: active.placeholder || undefined,
                ariaLabel: active.getAttribute('aria-label') || undefined
            };
        }
        """.replace('\n', ' ').strip()
        
        focused = await page.evaluate(js_focused)
        return focused if focused else {"info": "No element currently focused"}

async def get_main_content(page: Page) -> str:
    """
    Extract the main content of the page.
    """
    async with Timer("Get main content"):
        js_main_content = """
        () => {
            const mainSelectors = ['main', '[role="main"]', '#main-content', '#content', 'article', '.main-content'];
            for (const selector of mainSelectors) {
                const element = document.querySelector(selector);
                if (element) return element.innerText.substring(0, 1500);
            }
            const textNodes = Array.from(document.body.querySelectorAll('p, h1, h2, h3, h4, h5, h6'))
                .filter(el => el.innerText.trim().length > 0);
            if (textNodes.length > 0) {
                return textNodes.map(node => node.innerText).join('\\n\\n').substring(0, 1500);
            }
            return "No main content found";
        }
        """.replace('\n', ' ').strip()
        
        main_content = await page.evaluate(js_main_content)
        return main_content