from django.test import TestCase
from totem.uploads.admin import filename_to_title


class FilenameToTitleTests(TestCase):
    def test_simple_filename(self):
        result = filename_to_title("image.jpg")
        self.assertEqual(result, "Image")

    def test_filename_with_underscores(self):
        result = filename_to_title("my_image_file.png")
        self.assertEqual(result, "My Image File")

    def test_filename_with_hyphens(self):
        result = filename_to_title("my-image-file.jpg")
        self.assertEqual(result, "My Image File")

    def test_filename_with_mixed_separators(self):
        result = filename_to_title("my_image-file.webp")
        self.assertEqual(result, "My Image File")
