import os
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service


@pytest.fixture
def browser(request):
    options = webdriver.ChromeOptions()
    options.binary_location = '/usr/bin/chromium'
    options.accept_insecure_certs = True
    for argument in ['--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
                     '--window-size=1440,1000', '--lang=en-US']:
        options.add_argument(argument)
    driver = webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=options)
    driver.set_page_load_timeout(60)
    try:
        yield driver
    finally:
        destination = Path(os.getenv('REPORTS', 'lab7/artifacts')) / 'web'
        destination.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(destination / (request.node.name + '.png')))
        (destination / (request.node.name + '.html')).write_text(driver.page_source)
        driver.quit()
