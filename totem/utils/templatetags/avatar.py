from django import template

from totem.users.models import User

register = template.Library()


@register.inclusion_tag("utils/avatar.html")
def avatar(user: User, size=120, blank_ok=False, classes="", tooltip=False):
    size = int(size)
    ctx = {
        "size": size,
        "classes": classes,
        "name": user.name,
        "padding": f"{size / 1000}rem",
        "seed": user.profile_avatar_seed,
        "type": user.profile_avatar_type,
    }
    if tooltip:
        ctx["tooltip"] = True

    if user.profile_image:
        ctx["src"] = user.profile_image.url
    return ctx
