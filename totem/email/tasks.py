from .models import EmailActivity, EmailLog


def clear_old_logs():
    EmailLog.clear_old()
    EmailActivity.clear_old()


def backup_email_activity():
    EmailActivity.fetch_email_activity()


tasks = [clear_old_logs, backup_email_activity]
