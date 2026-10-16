"""Selenium CI checks adapted from lab 4: actual page content, not URL alone."""
import os
import re

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.getenv('BMC_URL', 'https://127.0.0.1:2443')
USER = (By.CSS_SELECTOR, "input#username, input[name='username'], input[data-test-id='login-input-username']")
PASSWORD = (By.CSS_SELECTOR, "input#password, input[name='password'], input[data-test-id='login-input-password']")
SUBMIT = (By.CSS_SELECTOR, "button[type='submit'], button[data-test-id='login-button-submit']")


def sign_in(browser, username, password):
    browser.get(BASE + '/#/login')
    wait = WebDriverWait(browser, 45)
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
    wait = sign_in(browser, 'lab7_nonexistent_user', 'deliberately-invalid')
    def visible_error(driver):
        return next((element for element in driver.find_elements(By.CSS_SELECTOR,
                     '.alert-danger, .invalid-feedback, [role="alert"]')
                     if element.is_displayed() and element.text.strip()), False)
    alert = wait.until(visible_error)
    assert alert.text.strip(), 'No error message for the rejected login'
    assert 'login' in browser.current_url
    assert browser.find_element(*USER).is_displayed()


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
    visible_rows = ' '.join(row.text for row in rows)
    assert re.search(r'\b42(?:\.0)?\b', visible_rows) and re.search(r'\b44(?:\.0)?\b', visible_rows)
