"""E2E tests for /chat.

Uses admin@test.local (chat.view is admin-only in the test seed). The Chat_*
tables are absent in TEST, so the conversation list is empty and the message
form stays hidden until a conversation is selected — tests target the always-
present "new conversation" control and the modal it opens.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_chat_renders(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/chat")
    expect(page.locator('[data-testid="chat-new-conversation"]')).to_be_visible()
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_chat_send_button_present_in_dom(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/chat")
    # The send control exists even though the input area is hidden until a
    # conversation is opened.
    expect(page.locator('[data-testid="chat-send"]')).to_be_attached()


@pytest.mark.flaky_e2e
def test_chat_new_conversation_opens_modal(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/chat")
    page.click('[data-testid="chat-new-conversation"]')
    expect(page.locator('[data-testid="chat-new-modal-cancel"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_chat_new_modal_cancel_closes(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/chat")
    page.click('[data-testid="chat-new-conversation"]')
    cancel = page.locator('[data-testid="chat-new-modal-cancel"]')
    expect(cancel).to_be_visible()
    cancel.click()
    expect(cancel).to_be_hidden()
