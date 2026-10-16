import os
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@pytest.fixture(scope='module')
def chrome():
    options = webdriver.ChromeOptions()
    options.binary_location = '/usr/bin/chromium'
    options.accept_insecure_certs = True
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    for argument in ['--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
                     '--window-size=1440,1000', '--lang=en-US']:
        options.add_argument(argument)
    driver = webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=options)
    driver.set_page_load_timeout(60)
    driver.get(os.getenv('BMC_URL', 'https://127.0.0.1:2443') + '/#/login')
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def browser(chrome, request):
    # Reuse the browser asset cache, but start every test without authentication.
    chrome.delete_all_cookies()
    chrome.execute_script('localStorage.clear(); sessionStorage.clear();')
    try:
        yield chrome
    finally:
        destination = Path(os.getenv('REPORTS', 'lab7/artifacts')) / 'web'
        destination.mkdir(parents=True, exist_ok=True)
        chrome.save_screenshot(str(destination / (request.node.name + '.png')))
        (destination / (request.node.name + '.html')).write_text(chrome.page_source)
        # End authenticated Web UI sessions through the actual application.
        logout = (By.CSS_SELECTOR, '[data-test-id="appHeader-link-logout"]')
        if chrome.find_elements(*logout):
            wait = WebDriverWait(chrome, 45, ignored_exceptions=(StaleElementReferenceException,))
            wait.until(EC.element_to_be_clickable((By.ID, 'app-header-user__BV_toggle_'))).click()
            wait.until(EC.element_to_be_clickable(logout)).click()
            wait.until(EC.visibility_of_element_located((By.ID, 'username')))
