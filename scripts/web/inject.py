import os
from playwright.sync_api import Page

def inject_input_interface(page: Page):
    """Inject a floating input interface into any webpage"""
    print("Injecting interface")
    # CSS to style our floating input box
    css = """
    #nyx-input-container {
        position: fixed;
        bottom: 10px; /* Move to the bottom */
        left: 50%; /* Center horizontally */
        transform: translateX(-50%); /* Adjust for centering */
        z-index: 2147483647;
        background: rgba(32, 33, 36, 0.9);
        padding: 6px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.5);
        display: flex;
        gap: 8px;
        align-items: center;
        width: 30%; /* Set the width to 30% of the browser width */
    }
    #nyx-input {
        flex: 1;
        min-width: 0;
        padding: 6px 10px;
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 4px;
        background: rgba(255,255,255,0.1);
        color: white;
        font-size: 14px;
        outline: none;
        transition: all 0.2s;
        width: 100%; /* Ensure the input takes the full width of the container */
    }
    #nyx-input:focus {
        background: rgba(255,255,255,0.15);
        border-color: #5e9fda;
    }
    #nyx-submit {
        padding: 6px 12px;
        border: none;
        border-radius: 4px;
        background: #3d85c6;
        color: white;
        font-size: 14px;
        cursor: pointer;
        transition: background 0.2s;
        white-space: nowrap;
        font-weight: 500;
    }
    #nyx-submit:hover {
        background: #5e9fda;
    }
    """
    
    # HTML for our input interface
    html = """
    <div id="nyx-input-container">
        <input type="text" id="nyx-input" placeholder="Enter command..." autocomplete="off" spellcheck="false">
        <button id="nyx-submit">Send</button>
    </div>
    """
    
    # JavaScript to handle input and expose it to Python
    js = """
    if (!window.nyxInput) {
        window.nyxInput = {
            lastCommand: null,
            commandProcessed: true,
            
            init() {
                const input = document.querySelector('#nyx-input');
                const submit = document.querySelector('#nyx-submit');

                const sendCommand = () => {
                    const command = input.value.trim();
                    if (command && this.commandProcessed) {
                        this.lastCommand = command;
                        this.commandProcessed = false;
                        input.value = '';
                    }
                };

                submit.addEventListener('click', sendCommand);
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        sendCommand();
                    }
                });

                // Focus input field
                setTimeout(() => input.focus(), 100);
            }
        };
    }
    window.nyxInput.init();
    """
    
    # Inject everything into the page
    page.evaluate(f"""
        () => {{
            const style = document.createElement('style');
            style.textContent = `{css}`;
            document.head.appendChild(style);
            
            document.body.insertAdjacentHTML('beforeend', `{html}`);
            
            {js}
        }}
    """)
    print("Interface injected")

def check_and_reinject(page: Page):
    """Check if interface exists and reinject if missing"""
    exists = page.evaluate("""() => {
        const inputContainer = document.getElementById('nyx-input-container');
        return inputContainer;
    }""")
    
    if not exists:
        # print("Interface not found, reinjecting")
        inject_input_interface(page)
    else:
        pass
        # print("Interface already exists")

def get_command(page: Page) -> str|None:
    """Check if there's a new command from the interface"""
    command = page.evaluate("() => window.nyxInput ? window.nyxInput.lastCommand : null")
    if command is not None:
        print(f"Command received: {command}")
    return command

def mark_command_processed(page: Page):
    """Mark the current command as processed"""
    page.evaluate("() => { if (window.nyxInput) { window.nyxInput.commandProcessed = true; window.nyxInput.lastCommand = null; } }")

def highlight_elements_batch(page: Page, elements_info, color='red', duration=5000):
    """Highlight multiple elements at once efficiently"""
    print(f"Highlighting elements: {elements_info}")
    
    js_highlight = f"""
    (elements_info) => {{
        if (!elements_info || !Array.isArray(elements_info)) {{
            console.error('Invalid elements_info:', elements_info);
            return;
        }}
        
        const divs = elements_info.filter(element => element && element.rect).map(element => {{
            const div = document.createElement('div');
            div.style.cssText = `
                position: absolute;
                z-index: 9999;
                border: 2px solid {color};
                pointer-events: none;
                left: ${{element.rect.x + window.scrollX}}px;
                top: ${{element.rect.y + window.scrollY}}px;
                width: ${{element.rect.width}}px;
                height: ${{element.rect.height}}px;
            `;
            document.body.appendChild(div);
            return div;
        }});
        
        setTimeout(() => {{
            divs.forEach(div => {{
                if (div && div.parentNode) {{
                    div.parentNode.removeChild(div);
                }}
            }});
        }}, {duration});
    }}
    """
    
    # Add error handling and logging
    try:
        page.evaluate(js_highlight, elements_info)
    except Exception as e:
        print(f"Error in highlight_elements_batch: {e}")
        print(f"elements_info: {elements_info}")
