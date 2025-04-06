import logging
from typing import Dict, Optional

import requests
from django.conf import settings

from .pool import global_pool

logger = logging.getLogger(__name__)
SLACK_API_URL_LOOKUP = "https://slack.com/api/users.lookupByEmail"
SLACK_API_URL_POST = "https://slack.com/api/chat.postMessage"
SLACK_BOT_TOKEN = settings.SLACK_BOT_TOKEN
SLACK_CHANNEL_ID = settings.SLACK_CHANNEL_ID

# Simple in-memory cache for email -> user_id mapping
USER_ID_CACHE: Dict[str, str] = {}

requests_session = requests.Session()


def notify_slack(message: str, email_to_mention: str | None = None):
    global_pool.add_task(_notify_task, message, email_to_mention)


def _notify_task(message: str, email_to_mention: str | None):
    logger.info("Sending message to Slack")
    _send_slack_message(
        message=message,
        email_to_mention=email_to_mention,
    )


def _get_user_id_from_email(email: str) -> Optional[str]:
    """
    Looks up a Slack User ID by email, using a cache.

    Args:
        email: The email address to look up.
        token: The Slack Bot OAuth token.

    Returns:
        The Slack User ID (e.g., 'U012ABCDEF') or None if not found or error.
    """
    if not email or not SLACK_BOT_TOKEN:
        logging.error("Email or token is missing for lookup.")
        return None

    # 1. Check cache first
    try:
        return USER_ID_CACHE[email]
    except KeyError:
        pass

    logging.info(f"Cache miss. Looking up user ID for email: {email}")
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    params = {"email": email}

    response = requests_session.get(SLACK_API_URL_LOOKUP, headers=headers, params=params, timeout=10)
    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

    data = response.json()

    if data.get("ok"):
        user_id = data.get("user", {}).get("id")
        if user_id:
            logging.info(f"Successfully found user ID: {user_id} for email: {email}")
            # 2. Cache the result
            USER_ID_CACHE[email] = user_id
            return user_id
        else:
            logging.warning(f"Could not find user ID for {email}, sending message without mention.")
            return None
    else:
        error_message = data.get("error", "unknown_error")
        if error_message == "users_not_found":
            logging.warning(f"Email {email} not found in Slack.")
            return None
        raise ValueError(f"Slack API error looking up email {email}: {error_message}")


def _send_slack_message(message: str, email_to_mention: Optional[str] = None) -> None:
    """
    Sends a message to a Slack channel, optionally mentioning a user by email.

    Args:
        message: The base message text.
        token: The Slack Bot OAuth token.
        channel_id: The ID of the target Slack channel.
        email_to_mention: The email address of the user to mention (optional).

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    if not SLACK_BOT_TOKEN:
        logger.info("Slack disabled")
        logger.info(f"SLACK MESSAGE: {message}, EMAIL: {email_to_mention}")
        return

    if not SLACK_CHANNEL_ID:
        raise ValueError("Slack token or channel ID is missing.")

    user_id_to_mention = None
    if email_to_mention:
        user_id_to_mention = _get_user_id_from_email(email_to_mention)

    # Construct the final message text
    final_message = message
    if user_id_to_mention:
        mention_string = f"<@{user_id_to_mention}>"
        # Prepend the mention to the original message
        final_message = f"{mention_string} {message}"
    elif email_to_mention:
        logging.warning(f"Could not find user ID for {email_to_mention}, sending message without mention.")
        # Keep final_message as the original message

    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json; charset=utf-8"}
    payload = {"channel": SLACK_CHANNEL_ID, "text": final_message}

    response = requests_session.post(SLACK_API_URL_POST, headers=headers, json=payload, timeout=10)
    response.raise_for_status()

    data = response.json()

    if data.get("ok"):
        logging.info(f"Message successfully sent to channel {SLACK_CHANNEL_ID}")
    else:
        error_message = data.get("error", "unknown_error")
        logging.error(f"Slack API error sending message: {error_message}")


# # --- Example Usage ---
# if __name__ == "__main__":
#     if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
#         print("Error: SLACK_BOT_TOKEN and SLACK_CHANNEL_ID environment variables must be set.")
#     else:
#         print("--- Running Slack Message Sender ---")

#         # Example 1: Simple message, no mention
#         print("\nTest 1: Sending simple message")
#         _send_slack_message(
#             message="Hello everyone, this is a general announcement.",
#             token=SLACK_BOT_TOKEN,
#             channel_id=SLACK_CHANNEL_ID,
#         )

#         # Example 2: Message with a valid email mention (replace with a real email in your workspace)
#         print("\nTest 2: Sending message with mention (first time lookup)")
#         valid_email = "bo@totem.org"  # <--- REPLACE WITH A VALID EMAIL
#         _send_slack_message(
#             message="Could you please look at this report?",
#             token=SLACK_BOT_TOKEN,
#             channel_id=SLACK_CHANNEL_ID,
#             email_to_mention=valid_email,
#         )

#         # Example 3: Message with the same valid email (should use cache)
#         print("\nTest 3: Sending message with mention again (should hit cache)")
#         _send_slack_message(
#             message="Just a reminder about the report.",
#             token=SLACK_BOT_TOKEN,
#             channel_id=SLACK_CHANNEL_ID,
#             email_to_mention=valid_email,  # Same email as before
#         )

#         # Example 4: Message with an invalid email mention
#         print("\nTest 4: Sending message with non-existent email")
#         invalid_email = "no.such.user@example.com"
#         _send_slack_message(
#             message="This task is assigned to the project lead.",  # Message sent without mention
#             token=SLACK_BOT_TOKEN,
#             channel_id=SLACK_CHANNEL_ID,
#             email_to_mention=invalid_email,
#         )

#         print("\n--- Finished ---")
#         print(f"Current User ID Cache: {USER_ID_CACHE}")
