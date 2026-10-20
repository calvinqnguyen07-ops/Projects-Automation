"""
Playwright (Python) + Pytest + Page Object Model (single-file example)
Target site: https://demo.playwright.dev/todomvc (official Playwright demo app)

SETUP
    pip install pytest-playwright
    playwright install chromium

RUN
    pytest test_todomvc_playwright.py -v                        # headless (default)
    pytest test_todomvc_playwright.py -v --headed               # watch it run
    pytest test_todomvc_playwright.py -v --browser firefox      # other browsers
    pytest test_todomvc_playwright.py -v --browser chromium --browser firefox --browser webkit
    pytest test_todomvc_playwright.py -v --screenshot only-on-failure --video retain-on-failure --tracing retain-on-failure

    View a trace from a failed test:
    playwright show-trace test-results/<test-folder>/trace.zip

WHY PLAYWRIGHT (vs Selenium)
    - Auto-waiting: no manual WebDriverWait code
    - Web-first assertions (expect) retry until they pass or time out
    - Built-in cross-browser support, tracing, video, screenshots
    - Locators based on what users see (role, label, text)
"""

import re

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "https://demo.playwright.dev/todomvc"


# --------------------------------------------------------------------------
# Page Object
# --------------------------------------------------------------------------
class TodoPage:
    def __init__(self, page: Page):
        self.page = page
        self.new_todo = page.get_by_placeholder("What needs to be done?")
        self.items = page.get_by_test_id("todo-item")
        self.titles = page.get_by_test_id("todo-title")
        self.count = page.get_by_test_id("todo-count")
        self.toggle_all = page.get_by_label("Mark all as complete")
        self.clear_completed = page.get_by_role("button", name="Clear completed")

    def open(self):
        self.page.goto(BASE_URL)
        expect(self.new_todo).to_be_visible()
        return self

    def add(self, *todos):
        for text in todos:
            self.new_todo.fill(text)
            self.new_todo.press("Enter")

    def item(self, index):
        return self.items.nth(index)

    def complete(self, index):
        self.item(index).get_by_role("checkbox").check()

    def delete(self, index):
        item = self.item(index)
        item.hover()  # the delete button only appears on hover
        item.get_by_role("button", name="Delete").click()

    def start_edit(self, index):
        self.item(index).get_by_test_id("todo-title").dblclick()
        return self.item(index).get_by_role("textbox", name="Edit")

    def filter_by(self, name):
        """name: All | Active | Completed"""
        self.page.get_by_role("link", name=name).click()


# --------------------------------------------------------------------------
# Fixture
# --------------------------------------------------------------------------
@pytest.fixture
def todo(page: Page) -> TodoPage:
    return TodoPage(page).open()


# --------------------------------------------------------------------------
# Adding todos
# --------------------------------------------------------------------------
def test_page_loads_empty(todo):
    expect(todo.items).to_have_count(0)
    expect(todo.new_todo).to_be_focused()


def test_add_single_todo(todo):
    todo.add("Buy milk")
    expect(todo.titles).to_have_text(["Buy milk"])
    expect(todo.new_todo).to_be_empty()  # input clears after adding


def test_add_multiple_todos_keeps_order(todo):
    todo.add("First", "Second", "Third")
    expect(todo.titles).to_have_text(["First", "Second", "Third"])


def test_empty_todo_is_not_added(todo):
    todo.new_todo.press("Enter")
    expect(todo.items).to_have_count(0)


def test_whitespace_is_trimmed(todo):
    todo.add("    padded text    ")
    expect(todo.titles).to_have_text(["padded text"])


@pytest.mark.parametrize(
    "text",
    ["Ünïcödé tëxt", "<b>not bold</b>", "Emoji 🚀 test", "a" * 100],
    ids=["unicode", "html-is-escaped", "emoji", "long-text"],
)
def test_add_special_text(todo, text):
    todo.add(text)
    expect(todo.titles).to_have_text([text])


# --------------------------------------------------------------------------
# Counter
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "todos, expected",
    [(["a"], "1 item left"), (["a", "b"], "2 items left"), (["a", "b", "c"], "3 items left")],
)
def test_counter_text(todo, todos, expected):
    todo.add(*todos)
    expect(todo.count).to_have_text(expected)


def test_counter_decreases_when_completing(todo):
    todo.add("a", "b", "c")
    todo.complete(0)
    expect(todo.count).to_have_text("2 items left")


# --------------------------------------------------------------------------
# Completing
# --------------------------------------------------------------------------
def test_complete_todo_adds_completed_class(todo):
    todo.add("Finish report")
    todo.complete(0)
    expect(todo.item(0)).to_have_class(re.compile(r"completed"))


def test_uncomplete_todo(todo):
    todo.add("Toggle me")
    todo.complete(0)
    todo.item(0).get_by_role("checkbox").uncheck()
    expect(todo.item(0)).not_to_have_class(re.compile(r"completed"))


def test_mark_all_as_complete(todo):
    todo.add("a", "b", "c")
    todo.toggle_all.check()
    for i in range(3):
        expect(todo.item(i)).to_have_class(re.compile(r"completed"))
    expect(todo.count).to_have_text("0 items left")


# --------------------------------------------------------------------------
# Editing and deleting
# --------------------------------------------------------------------------
def test_edit_todo(todo):
    todo.add("Old title")
    editor = todo.start_edit(0)
    editor.fill("New title")
    editor.press("Enter")
    expect(todo.titles).to_have_text(["New title"])


def test_escape_cancels_edit(todo):
    todo.add("Keep me")
    editor = todo.start_edit(0)
    editor.fill("Changed my mind")
    editor.press("Escape")
    expect(todo.titles).to_have_text(["Keep me"])


def test_editing_to_empty_deletes_todo(todo):
    todo.add("Delete via edit")
    editor = todo.start_edit(0)
    editor.fill("")
    editor.press("Enter")
    expect(todo.items).to_have_count(0)


def test_delete_todo(todo):
    todo.add("a", "b", "c")
    todo.delete(1)
    expect(todo.titles).to_have_text(["a", "c"])


# --------------------------------------------------------------------------
# Filters and clearing
# --------------------------------------------------------------------------
def test_filters_show_correct_items(todo):
    todo.add("active one", "done one", "active two")
    todo.complete(1)

    todo.filter_by("Active")
    expect(todo.titles).to_have_text(["active one", "active two"])

    todo.filter_by("Completed")
    expect(todo.titles).to_have_text(["done one"])

    todo.filter_by("All")
    expect(todo.items).to_have_count(3)


def test_filter_updates_url(todo):
    todo.add("anything")
    todo.filter_by("Completed")
    expect(todo.page).to_have_url(re.compile(r"#/completed$"))


def test_clear_completed(todo):
    todo.add("keep", "remove", "remove too")
    todo.complete(1)
    todo.complete(2)
    todo.clear_completed.click()
    expect(todo.titles).to_have_text(["keep"])
    expect(todo.clear_completed).to_be_hidden()


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
def test_todos_persist_after_reload(todo):
    todo.add("Survive reload", "Me too")
    todo.complete(0)

    todo.page.reload()

    expect(todo.titles).to_have_text(["Survive reload", "Me too"])
    expect(todo.item(0)).to_have_class(re.compile(r"completed"))


# --------------------------------------------------------------------------
# Accessibility smoke check
# --------------------------------------------------------------------------
def test_page_has_expected_title_and_heading(todo):
    expect(todo.page).to_have_title(re.compile("TodoMVC"))
    expect(todo.page.get_by_role("heading", name="todos")).to_be_visible()
