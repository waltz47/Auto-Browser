functions = [
    {
        "type": "function",
        "function": {
            "name": "move_to_url",
            "description": "Set a specific URL as the active page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to.",
                        "example_value": "https://example.com",
                    },
                },
                "required": ["url"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_url_contents",
            "description": "Get the contents from the active page.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "optional": [],
            },
        }
    },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "set_element",
    #         "description": "Set a page element as active.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "xpathSelector": {
    #                     "type": "string",
    #                     "description": "The xpath selector for an element.",
    #                     "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]",
    #                 },
    #             },
    #             "required": ["xpathSelector"],
    #             "optional": [],
    #         },
    #     }
    # },
    {
        "type": "function",
        "function": {
            "name": "send_keys_to_element",
            "description": "Send keys to element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    },
                    "keys": {
                        "type": "string",
                        "description": "The keys to send to the element.",
                        "example_value": "Hello, World!",
                    }
                },
                "required": ["xpathSelector", "keys"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_submit",
            "description": "Call submit on an element. Usually used on forms after entering the text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    }
                },
                "required": ["xpathSelector"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    }
                },
                "required": ["xpathSelector"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "highlight_element",
            "description": "Highlight an element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    }
                },
                "required": ["xpathSelector"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_and_click_at_page_position",
            "description": "Moves cursor to a page element and clicks",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_x": {
                        "type": "number",
                        "description": "The X coordinate of the element",
                        "example_value": "56"
                    },
                    "location_y": {
                        "type": "number",
                        "description": "The y coordinate of the element",
                        "example_value": "55"
                    }
                },
                "required": ["location_x", "location_y"],
                "optional": [],
            },
        }
    },

]

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