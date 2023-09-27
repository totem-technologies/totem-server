from io import BytesIO

from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.main import QRCode


def make_qr(data):
    qr = QRCode(
        version=None,
        box_size=14,
        border=1,
    )
    qr.add_data(data)
    img = qr.make_image(
        fit=True,
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        color_mask=SolidFillColorMask(back_color=(255, 255, 255, 0), front_color=(0, 0, 0, 255)),
    )
    buffered = BytesIO()
    img.save(
        buffered,
        format="png",
        optimize=True,
    )
    return buffered.getvalue()
