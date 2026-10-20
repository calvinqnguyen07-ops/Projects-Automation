"""
Selenium + Pytest + Page Object Model (single-file example)
Target site: https://www.saucedemo.com (public demo e-commerce site)

SETUP
    pip install selenium pytest

RUN
    pytest test_saucedemo.py -v                 # Chrome, visible
    HEADLESS=1 pytest test_saucedemo.py -v      # Chrome, headless
    pytest test_saucedemo.py -v -k checkout     # run a subset

NOTES
    - Selenium 4.6+ downloads the matching chromedriver automatically.
    - Screenshots of failed tests are saved to ./screenshots/
"""

import os
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE_URL = "https://www.saucedemo.com"
PASSWORD = "secret_sauce"
SCREENSHOT_DIR = Path("screenshots")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def driver(request):
    options = Options()
    if os.getenv("HEADLESS"):
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-search-engine-choice-screen")
    options.add_experimental_option(
        "prefs",
        {"credentials_enable_service": False, "profile.password_manager_enabled": False},
    )

    drv = webdriver.Chrome(options=options)
    drv.implicitly_wait(0)  # explicit waits only

    failed_before = request.session.testsfailed
    yield drv

    # Screenshot if this test failed
    if request.session.testsfailed > failed_before:
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        drv.save_screenshot(str(SCREENSHOT_DIR / f"{request.node.name}.png"))
    drv.quit()


# --------------------------------------------------------------------------
# Page Objects
# --------------------------------------------------------------------------
class BasePage:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    def find(self, locator):
        return self.wait.until(EC.visibility_of_element_located(locator))

    def click(self, locator):
        self.wait.until(EC.element_to_be_clickable(locator)).click()

    def type(self, locator, text):
        el = self.find(locator)
        el.clear()
        el.send_keys(text)

    def text_of(self, locator):
        return self.find(locator).text


class LoginPage(BasePage):
    USERNAME = (By.ID, "user-name")
    PASSWORD = (By.ID, "password")
    SUBMIT = (By.ID, "login-button")
    ERROR = (By.CSS_SELECTOR, "[data-test='error']")

    def open(self):
        self.driver.get(BASE_URL)
        return self

    def login(self, username, password=PASSWORD):
        self.type(self.USERNAME, username)
        self.type(self.PASSWORD, password)
        self.click(self.SUBMIT)

    def error_message(self):
        return self.text_of(self.ERROR)


class InventoryPage(BasePage):
    TITLE = (By.CSS_SELECTOR, ".title")
    ITEMS = (By.CSS_SELECTOR, ".inventory_item")
    PRICES = (By.CSS_SELECTOR, ".inventory_item_price")
    NAMES = (By.CSS_SELECTOR, ".inventory_item_name")
    SORT = (By.CSS_SELECTOR, "[data-test='product-sort-container']")
    ADD_BUTTONS = (By.CSS_SELECTOR, "button[data-test^='add-to-cart']")
    CART_BADGE = (By.CSS_SELECTOR, ".shopping_cart_badge")
    CART_LINK = (By.CSS_SELECTOR, ".shopping_cart_link")

    def title(self):
        return self.text_of(self.TITLE)

    def item_count(self):
        self.find(self.ITEMS)
        return len(self.driver.find_elements(*self.ITEMS))

    def sort_by(self, value):
        """value: az | za | lohi | hilo"""
        Select(self.find(self.SORT)).select_by_value(value)

    def prices(self):
        self.find(self.PRICES)
        return [float(e.text.replace("$", "")) for e in self.driver.find_elements(*self.PRICES)]

    def names(self):
        self.find(self.NAMES)
        return [e.text for e in self.driver.find_elements(*self.NAMES)]

    def add_first_n_items(self, n):
        self.find(self.ADD_BUTTONS)
        for button in self.driver.find_elements(*self.ADD_BUTTONS)[:n]:
            button.click()

    def cart_count(self):
        badges = self.driver.find_elements(*self.CART_BADGE)
        return int(badges[0].text) if badges else 0

    def open_cart(self):
        self.click(self.CART_LINK)


class CartPage(BasePage):
    ITEMS = (By.CSS_SELECTOR, ".cart_item")
    CHECKOUT = (By.ID, "checkout")

    def item_count(self):
        self.find((By.CSS_SELECTOR, ".cart_list"))
        return len(self.driver.find_elements(*self.ITEMS))

    def checkout(self):
        self.click(self.CHECKOUT)


class CheckoutPage(BasePage):
    FIRST = (By.ID, "first-name")
    LAST = (By.ID, "last-name")
    ZIP = (By.ID, "postal-code")
    CONTINUE = (By.ID, "continue")
    FINISH = (By.ID, "finish")
    ERROR = (By.CSS_SELECTOR, "[data-test='error']")
    COMPLETE = (By.CSS_SELECTOR, ".complete-header")

    def fill_info(self, first, last, postal):
        self.type(self.FIRST, first)
        self.type(self.LAST, last)
        self.type(self.ZIP, postal)
        self.click(self.CONTINUE)

    def finish(self):
        self.click(self.FINISH)

    def error_message(self):
        return self.text_of(self.ERROR)

    def confirmation(self):
        return self.text_of(self.COMPLETE)


# --------------------------------------------------------------------------
# Helper fixture: logged-in inventory page
# --------------------------------------------------------------------------
@pytest.fixture
def inventory(driver):
    LoginPage(driver).open().login("standard_user")
    return InventoryPage(driver)


# --------------------------------------------------------------------------
# Tests: Login
# --------------------------------------------------------------------------
def test_valid_login(driver):
    LoginPage(driver).open().login("standard_user")
    assert InventoryPage(driver).title() == "Products"
    assert "/inventory.html" in driver.current_url


@pytest.mark.parametrize(
    "username, password, expected_error",
    [
        ("standard_user", "wrong_password", "Username and password do not match"),
        ("not_a_user", PASSWORD, "Username and password do not match"),
        ("", PASSWORD, "Username is required"),
        ("standard_user", "", "Password is required"),
        ("locked_out_user", PASSWORD, "this user has been locked out"),
    ],
    ids=["bad-password", "bad-username", "empty-username", "empty-password", "locked-out"],
)
def test_invalid_login(driver, username, password, expected_error):
    page = LoginPage(driver).open()
    page.login(username, password)
    assert expected_error in page.error_message()


# --------------------------------------------------------------------------
# Tests: Inventory
# --------------------------------------------------------------------------
def test_inventory_shows_six_products(inventory):
    assert inventory.item_count() == 6


def test_sort_price_low_to_high(inventory):
    inventory.sort_by("lohi")
    prices = inventory.prices()
    assert prices == sorted(prices)


def test_sort_name_z_to_a(inventory):
    inventory.sort_by("za")
    names = inventory.names()
    assert names == sorted(names, reverse=True)


# --------------------------------------------------------------------------
# Tests: Cart & Checkout
# --------------------------------------------------------------------------
def test_cart_badge_updates(inventory):
    assert inventory.cart_count() == 0
    inventory.add_first_n_items(3)
    assert inventory.cart_count() == 3


def test_cart_contains_added_items(driver, inventory):
    inventory.add_first_n_items(2)
    inventory.open_cart()
    assert CartPage(driver).item_count() == 2


def test_checkout_requires_first_name(driver, inventory):
    inventory.add_first_n_items(1)
    inventory.open_cart()
    CartPage(driver).checkout()
    checkout = CheckoutPage(driver)
    checkout.fill_info("", "Doe", "12345")
    assert "First Name is required" in checkout.error_message()


def test_full_checkout_flow(driver, inventory):
    inventory.add_first_n_items(2)
    inventory.open_cart()
    CartPage(driver).checkout()

    checkout = CheckoutPage(driver)
    checkout.fill_info("Jane", "Doe", "90210")
    checkout.finish()

    assert checkout.confirmation() == "Thank you for your order!"
