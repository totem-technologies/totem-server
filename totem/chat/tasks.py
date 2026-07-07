# Chat tasks are handled synchronously during message sending.
# Notifications are dispatched inline via notify_users().
# No periodic tasks are required for the chat system at this time.

tasks: list = []
