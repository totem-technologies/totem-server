from .models import ActionToken, LoginPin


def cleanup_actions():
    ActionToken.cleanup()


def cleanup_pins():
    LoginPin.cleanup()


tasks = [cleanup_actions, cleanup_pins]
