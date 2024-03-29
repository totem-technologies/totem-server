import random
import urllib.parse

from django import template
from django.template import Context
from django.template.engine import Engine
from django.templatetags.static import static

from totem.users.models import User
from totem.utils.hash import basic_hash

register = template.Library()


@register.inclusion_tag("utils/avatar.html")
def avatar(user: User, size=120, blank_ok=False, classes=""):
    current_engine = Engine.get_default()
    size = int(size)
    ctx = {"size": size, "classes": classes, "name": user.name, "padding": f"{size / 1000}rem"}
    if user.profile_avatar_type == User.ProfileChoices.IMAGE:
        if user.profile_image:
            ctx["src"] = user.profile_image.url
        else:
            ctx["src"] = static("images/default_profile.webp")
    else:
        # Render the avatar as a data URI SVG in an img tag. Using raw SVG causes React to not render the SVG properly.
        avatar_ctx = avatar_marble(salt=str(user.profile_avatar_seed), size=size)
        svg = current_engine.select_template(["utils/avatar.svg"]).render(Context(avatar_ctx))
        ctx["src"] = f"data:image/svg+xml;utf8,{urllib.parse.quote(svg)}"
    return ctx


ELEMENTS = 3
SIZE = 80

_themes = [
    ["A7C5C5", "DEE0D5", "E2AC48", "B96028", "983C2D"],
    ["416067", "A76A59", "72E790", "F4EC8D", "CC84CD"],
    ["3C8FDD", "6FBEEE", "DDEAF3", "B9BC88", "D8C5A5"],
    ["D94A70", "BF50A2", "B284BF", "6C8C3B", "D3D92B"],
    ["191726", "121D40", "295073", "517C8C", "E8F2D0"],
    ["98A8D9", "FBCF8E", "7E2F82", "CC8B82", "BF2B0A"],
    ["F2F2F2", "B5B4AC", "4A4436", "BE5C3D", "242124"],
    ["26C4A5", "54D99F", "ACE08C", "E8E284", "F2B652"],
    ["7CB9C8", "272B61", "EA6945", "9C797C", "6A98AF"],
    ["6FA0BD", "B4D8F3", "5D7C8D", "758D21", "9BA453"],
    ["FFBE4C", "B33127", "93EDFF", "648FAD", "FFFFFF"],
    ["1AAACF", "FF2135", "FFE400", "12E895", "F3FFE2"],
    ["F40000", "8C1278", "FFCB25", "F76516", "FFFFFF"],
    ["F30013", "FC0246", "FB418E", "D2D941", "FCB41F"],
    ["7D462B", "B3643E", "524235", "836654", "9A8570"],
    ["F2D022", "F28705", "F25C05", "BF1304", "0D0D0D"],
    ["1D1C53", "89356E", "04BFBF", "FFB248", "FFD700"],
    ["E8E402", "E2FF02", "FFEE0F", "E8CC02", "FFD300"],
    ["9E00CE", "5DDB00", "AED3DF", "CC5400", "DEFF00"],
    ["DA6E65", "F5D469", "E18A41", "2EC9D0", "B8EDE9"],
    ["05D6C4", "F79D04", "FA8806", "F3A259", "EF8F6A"],
    ["D3B8AD", "E37E33", "CAC658", "928B39", "EBB12B"],
    ["FFB1A8", "D96D48", "FFC753", "087D6F", "F9F2E6"],
    ["CCC11E", "999663", "FFCC3F", "7EBBFF", "1E9ECC"],
    ["EF4136", "14313F", "D89060", "BFB2A9", "276660"],
    ["7A98BF", "EBD56D", "DA8B17", "BF1F1F", "D96262"],
    ["CCAC14", "99893D", "FF9F00", "40D4FF", "6CCCC8"],
    ["11ADA4", "FF29DD", "CFFAF7", "C7A81E", "BBB59B"],
    ["6387A6", "C5E2E6", "F2E4BB", "F2B66D", "F28157"],
    ["686C6A", "8EB7FB", "FEFEFE", "F2B705", "FE4C04"],
    ["9DFFA0", "31B334", "60FF64", "B32063", "FFADD3"],
    ["BF0335", "021826", "D7EDF2", "0C7F8C", "F23535"],
    ["FEFF59", "FFD947", "FFD08F", "FF9369", "FF4A56"],
    ["BD464C", "E2DED3", "F5CC74", "7C777D", "8D9FB5"],
    ["7A9949", "F5F5AF", "FFDA45", "FFF17C", "9CC1CC"],
    ["707F8C", "BFA68F", "73482F", "732C26", "401919"],
    ["F2055C", "F2C5C7", "A3D9D3", "04CFBA", "03ABA2"],
    ["B1A612", "57091E", "A4002C", "0B5871", "0CB9F0"],
    ["81B854", "D6FAB9", "CBFFA1", "B37FB8", "F6C8FA"],
    ["366E93", "F2F2F2", "3B442F", "73412F", "BF5454"],
    ["E87351", "E89F51", "FFC359", "FF6659", "FF9E66"],
    ["EEDEFF", "E2A3F0", "FFA4E2", "EBB2B5", "FFBCAD"],
    ["F5BDC1", "88A79F", "EF9A63", "F1AE88", "F3F3F3"],
    ["9BE3FC", "597A34", "413A27", "85310C", "776050"],
    ["038C73", "277365", "CEF2E1", "BF9004", "A62F03"],
    ["FF5700", "60FF3C", "46F8FF", "967EA1", "FFF000"],
    ["8BB6E8", "83DCFF", "FF9761", "E8E357", "CB63FF"],
    ["A83200", "FF5E19", "F54900", "00A892", "00F5D5"],
    ["BF8FAF", "308C83", "21BFA2", "F2C230", "D9AD2B"],
    ["FFDDCF", "96BFD3", "4D3A2F", "EE9D8A", "185A72"],
    ["011140", "16498C", "F2E530", "F2B705", "D97904"],
    ["323940", "516673", "64734D", "778C49", "BFB78F"],
    ["FFFFE8", "74ECEE", "FFB8C3", "9DAFFC", "35D0FF"],
    ["F23D91", "FFB0C7", "93BF9A", "BED984", "FFB959"],
    ["F2CB05", "F2B705", "F29F05", "F27405", "D95204"],
    ["FFEDE6", "E8D4D1", "E8D1DC", "FFFFFF", "FFE6FF"],
    ["B35B72", "FFFAB5", "FF9CB5", "68B3CC", "2991B3"],
    ["94CEF2", "EDE0D2", "067368", "048C73", "8C7A20"],
    ["FFBF00", "FF1700", "320000", "1C7E79", "00D3BA"],
    ["820000", "DA0136", "EC1050", "FF3A72", "F578A2"],
    ["FD4501", "F66D39", "FE0000", "F96969", "FE5353"],
    ["E00724", "6DA68B", "D1D99A", "EFBF2F", "F98700"],
    ["C20016", "FF0321", "8FFF20", "08CC6C", "088C4A"],
    ["77C26F", "4A4C4B", "FBFFFF", "C8C9CD", "9FA3A6"],
    ["E022A7", "E0AC4F", "E037AC", "3CE022", "2D7FE0"],
    ["42DB87", "1FA3DB", "DBDB37", "545454", "E8A456"],
    ["1B4001", "365902", "618C03", "83A603", "97BF04"],
    ["FEEB5A", "91CED9", "D2190F", "1A1A1A", "FFFFFF"],
    ["197373", "02734A", "F2B90C", "F25116", "D91C0B"],
    ["A32910", "FF6B4D", "F04F30", "00A362", "41F0AA"],
    ["DB9079", "DBD55E", "DB6A48", "32DBAF", "743DDB"],
]


def hash_code(name) -> int:
    hash_ = 0
    for character in name:
        hash_ = ((hash_ << 5) - hash_) + ord(character)
        hash_ = hash_ & hash_  # Convert to 32-bit integer
    return abs(hash_)


def _generate_colors(key, colors):
    range_ = len(colors) if colors else None

    elements_properties = []
    for i in range(ELEMENTS):
        color = get_random_color(key + i, colors, range_)
        translate_x = get_unit(key * (i + 1), SIZE / 10, 1)
        translate_y = get_unit(key * (i + 1), SIZE / 10, 2)
        scale = 1.2 + get_unit(key * (i + 1), SIZE / 20) / 10
        rotate = get_unit(key * (i + 1), 360, 1)
        elements_properties.append(
            {
                "color": "#" + color,
                "translateX": translate_x,
                "translateY": translate_y,
                "scale": scale,
                "rotate": rotate,
            }
        )

    return elements_properties


def get_random_color(seed, colors, range_=None):
    random.seed(seed)
    if range_:
        return colors[random.randint(0, range_ - 1)]
    else:
        return "#" + "".join(random.choices("0123456789ABCDEF", k=6))


def get_unit(seed, max_value, decimal_places=0):
    random.seed(seed)
    return round(random.uniform(0, max_value), decimal_places)


def avatar_marble(
    salt: str,
    colors: list | None = None,
    size: int = 120,
):
    hashed_key = int(basic_hash(salt, as_int=True))
    if not colors:
        colors = _themes[hashed_key % len(_themes)]
    properties = _generate_colors(hashed_key, colors)
    mask_id = "mask_" + str(hashed_key)

    return {
        "size": size,
        "SIZE": SIZE,
        "SIZED2": SIZE / 2,
        "RX": SIZE * 2,
        "salt": salt,
        "properties": properties,
        "mask_id": mask_id,
    }


if __name__ == "__main__":
    print(
        avatar_marble(
            salt="test",
            size=80,
        )
    )
