from .models import ActionToken


def cleanup_actions():
    ActionToken.cleanup()


tasks = [cleanup_actions]
