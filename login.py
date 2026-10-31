from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cookies file
COOKIES_JSON_FILE = "cookies.json"

def get_driver():
    chrome_options = webdriver.ChromeOptions()
    # Disable automation flags to avoid detection
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    
    # Initialize driver
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    
    # Hide webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def save_cookies(driver, json_path):
    cookies = driver.get_cookies()
    with open(json_path, 'w') as file:
        json.dump(cookies, file, indent=4)
    logger.info(f"Cookies saved to {json_path}")

def main():
    driver = None
    try:
        driver = get_driver()
        # Open TradingView Arabic version
        driver.get("https://app.webull.com/stocks")
        logger.info("Opened TradingView. Please log in within 60 seconds.")
        
        # Wait for manual login
        time.sleep(300)
        
        # Save cookies to JSON file
        save_cookies(driver, COOKIES_JSON_FILE)
        
        logger.info("Cookies saved successfully. You can now close the browser.")
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    
    finally:
        if driver is not None:
            driver.quit()

if __name__ == '__main__':
    main()