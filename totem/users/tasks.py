from oauth2_provider.models import clear_expired

from .models import ActionToken


def cleanup_actions():
    ActionToken.cleanup()


def cleanup_oauth_tokens():
    clear_expired()


tasks = [cleanup_actions, cleanup_oauth_tokens]
