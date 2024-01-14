from .models import EmailLog


def clear_old_email_logs():
    EmailLog.clear_old()


tasks = [clear_old_email_logs]
