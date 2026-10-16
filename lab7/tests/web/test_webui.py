"""Selenium CI checks adapted from lab 4: actual page content, not URL alone."""
import os
import json
from pathlib import Path
from urllib.parse import urlsplit
import re

import pytest
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.getenv('BMC_URL', 'https://127.0.0.1:2443')
USER = (By.CSS_SELECTOR, "input#username, input[name='username'], input[data-test-id='login-input-username']")
PASSWORD = (By.CSS_SELECTOR, "input#password, input[name='password'], input[data-test-id='login-input-password']")
SUBMIT = (By.CSS_SELECTOR, "button[type='submit'], button[data-test-id='login-button-submit']")


def sign_in(browser, username, password):
    browser.get(BASE + '/#/login')
    wait = WebDriverWait(browser, 45, ignored_exceptions=(StaleElementReferenceException,))
    wait.until(EC.visibility_of_element_located(USER)).send_keys(username)
    browser.find_element(*PASSWORD).send_keys(password)
    wait.until(EC.element_to_be_clickable(SUBMIT)).click()
    return wait


@pytest.fixture
def logged_in(browser):
    wait = sign_in(browser, os.getenv('BMC_USERNAME', 'root'), os.environ['BMC_PASSWORD'])
    wait.until(lambda driver: 'login' not in driver.current_url)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='server-power-operations']")))
    return browser


def test_valid_login(logged_in):
    assert 'login' not in logged_in.current_url
    assert logged_in.find_elements(By.CSS_SELECTOR, "a[href*='hardware-status/sensors']")


def test_invalid_login(browser):
    # The Vue authentication interceptor reloads the page on HTTP 401. Assert
    # the real rejected login response instead of retaining an obsolete alert.
    wait = sign_in(browser, 'invalid_ci', 'deliberately-invalid')
    rejected = {}
    def rejected_login(driver):
        for entry in driver.get_log('performance'):
            event = json.loads(entry['message'])['message']
            if event['method'] == 'Network.responseReceived':
                response = event['params']['response']
                path = urlsplit(response['url']).path
                if path in ['/login', '/redfish/v1/SessionService/Sessions']:
                    status = int(response['status'])
                    if status in [401, 403]:
                        rejected.update(login_path=path, login_status=status)
        return bool(rejected)
    wait.until(rejected_login)
    wait.until(EC.visibility_of_element_located(USER))
    assert 'login' in browser.current_url
    # A retained login form alone would not prove that access is denied.
    status = browser.execute_async_script("""
        const done = arguments[arguments.length - 1];
        fetch('/redfish/v1/Systems/system', {credentials: 'same-origin'})
          .then(response => done(response.status)).catch(() => done(0));
    """)
    assert status in [401, 403], f'Unauthenticated protected resource returned {status}'
    rejected['protected_resource_status'] = status
    destination = Path(os.getenv('REPORTS', 'lab7/artifacts')) / 'web'
    destination.mkdir(parents=True, exist_ok=True)
    # Raw performance logs can contain login request data and are never saved.
    (destination / 'rejected-login.json').write_text(json.dumps(rejected, indent=2) + '\n')


def test_power_controls(logged_in):
    logged_in.get(BASE + '/#/operations/server-power-operations')
    wait = WebDriverWait(logged_in, 45)
    wait.until(lambda driver: any('power on' in e.text.lower()
               for e in driver.find_elements(By.CSS_SELECTOR, 'button')))
    assert 'server power operations' in logged_in.find_element(By.TAG_NAME, 'body').text.lower()


def test_cpu_sensors(logged_in):
    logged_in.get(BASE + '/#/hardware-status/sensors')
    wait = WebDriverWait(logged_in, 45)
    def both_cpus(driver):
        body = driver.find_element(By.TAG_NAME, 'body').text.lower()
        normalized = re.sub(r'[^a-z0-9]', '', body)
        return all(name in normalized for name in ['p0core0temp', 'p1core0temp'])
    wait.until(both_cpus)
    rows = logged_in.find_elements(By.CSS_SELECTOR, 'tbody tr')
    assert len(rows) >= 2, 'CPU sensor rows are missing'
    for name, value in [('p0core0temp', 42), ('p1core0temp', 44)]:
        matches = [row.text for row in rows if name in re.sub(r'[^a-z0-9]', '', row.text.lower())]
        assert len(matches) == 1, f'Missing or ambiguous CPU row: {name}'
        assert re.search(rf'(?<![\d.]){value}(?:\.0+)?(?![\d.])', matches[0]), matches[0]
