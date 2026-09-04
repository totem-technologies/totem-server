from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from totem.users.tests.factories import UserFactory

from .factories import BlogPostFactory


class BlogPostModelTests(TestCase):
    def test_default_publish_status(self):
        post = BlogPostFactory()
        self.assertFalse(post.publish)

    def test_read_time_auto_calculation(self):
        # Test with short content (should be 1 minute minimum)
        post = BlogPostFactory(content="Short content.")
        self.assertEqual(post.read_time, 1)

        # Test with ~225 words (should be 1 minute)
        content_225_words = " ".join(["word"] * 225)
        post = BlogPostFactory(content=content_225_words)
        self.assertEqual(post.read_time, 1)

        # Test with ~450 words (should be 2 minutes)
        content_450_words = " ".join(["word"] * 450)
        post = BlogPostFactory(content=content_450_words)
        self.assertEqual(post.read_time, 2)

        # Test with ~1125 words (should be 5 minutes)
        content_1125_words = " ".join(["word"] * 1125)
        post = BlogPostFactory(content=content_1125_words)
        self.assertEqual(post.read_time, 5)

    def test_read_time_updates_on_save(self):
        # Create post with short content
        post = BlogPostFactory(content="Short.")
        self.assertEqual(post.read_time, 1)

        # Update content to be longer
        post.content = " ".join(["word"] * 900)  # ~4 minutes
        post.save()
        self.assertEqual(post.read_time, 4)

        # Update back to short content
        post.content = "Very short."
        post.save()
        self.assertEqual(post.read_time, 1)

    def test_read_time_strips_markdown(self):
        # Test that markdown formatting is properly stripped before calculation
        markdown_content = """
        ## Header Two
        ### Header Three

        This is a [link](https://example.com) and this is **bold** text.
        Here's some _italic_ text and `inline code`.

        ```python
        def example():
            # This code block should be ignored
            return "ignored"
        ```

        ![Image description](https://example.com/image.jpg)

        - List item 1
        - List item 2
        * Another list item

        > This is a blockquote

        Regular paragraph with ~strikethrough~ and more content.
        """ + " ".join(["word"] * 200)  # Add more words to test calculation

        post = BlogPostFactory(content=markdown_content)
        # Should calculate based on actual text content, not markdown syntax
        # The markdown content above has roughly 30-40 words plus 200 added words
        # Should be around 1-2 minutes
        self.assertLessEqual(post.read_time, 2)
        self.assertGreaterEqual(post.read_time, 1)

    def test_read_time_handles_template_tags(self):
        # Test content with Django template tags (like the image tag mentioned in help text)
        content_with_tags = """
        ## Blog Post

        Here's some content with an image {% image slug="vji504tvi" %} embedded.

        More content here with another {% image slug="abc123" %} tag.
        """ + " ".join(["word"] * 250)

        post = BlogPostFactory(content=content_with_tags)
        # Should handle template tags gracefully
        self.assertGreaterEqual(post.read_time, 1)
        self.assertLessEqual(post.read_time, 3)

    def test_string_representation(self):
        post = BlogPostFactory(title="Test Post")
        self.assertEqual(str(post), "Test Post")

    def test_get_absolute_url(self):
        post = BlogPostFactory()
        self.assertEqual(post.get_absolute_url(), f"/blog/{post.slug}/")

    def test_markdown_validation(self):
        # Test invalid H1 header
        with self.assertRaisesMessage(ValidationError, "H1 headers"):
            BlogPostFactory(content="# Invalid Header").full_clean()

        # Test valid content
        BlogPostFactory(content="## Valid H2 Header\nProper content").full_clean()


class BlogViewTests(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True)
        self.user = UserFactory()
        self.published_post = BlogPostFactory(publish=True)
        self.unpublished_post = BlogPostFactory(publish=False)

    def test_list_view_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("blog:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.published_post.title)
        self.assertContains(response, self.unpublished_post.title)

    def test_list_view_regular_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("blog:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.published_post.title)
        self.assertNotContains(response, self.unpublished_post.title)

    def test_detail_view_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.unpublished_post.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_detail_view_regular_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.unpublished_post.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_ordering(self):
        older_post = BlogPostFactory(
            date_published=self.published_post.date_published - timedelta(days=1), publish=True
        )
        older_post.save()
        response = self.client.get(reverse("blog:list"))
        posts = response.context["posts"]
        self.assertEqual(posts[0], self.published_post)
        self.assertEqual(posts[1], older_post)

    def test_archive_lists_every_published_post(self):
        # The list view paginates, the archive does not: every post is one
        # click away so search engines can reach all of them.
        base = self.published_post.date_published
        posts = [BlogPostFactory(publish=True, date_published=base - timedelta(days=i)) for i in range(1, 20)]
        response = self.client.get(reverse("blog:archive"))
        self.assertEqual(response.status_code, 200)
        for post in posts + [self.published_post]:
            self.assertContains(response, post.title)
            self.assertContains(response, post.get_absolute_url())
        self.assertNotContains(response, self.unpublished_post.title)

    def test_archive_is_one_query(self):
        # Authors render as avatars on every row, so they must come along
        # with the posts instead of one query per row.
        for i in range(1, 6):
            BlogPostFactory(publish=True, date_published=self.published_post.date_published - timedelta(days=i))
        with self.assertNumQueries(1):
            self.client.get(reverse("blog:archive"))

    def test_archive_staff_sees_drafts(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("blog:archive"))
        self.assertContains(response, self.unpublished_post.title)
        self.assertContains(response, "[DRAFT]")

    def test_list_links_to_archive(self):
        response = self.client.get(reverse("blog:list"))
        self.assertContains(response, reverse("blog:archive"))

    def test_detail_links_to_older_and_newer_posts(self):
        base = self.published_post.date_published
        older = BlogPostFactory(publish=True, date_published=base - timedelta(days=2))
        draft_between = BlogPostFactory(publish=False, date_published=base - timedelta(days=1))
        newer = BlogPostFactory(publish=True, date_published=base + timedelta(days=1))

        response = self.client.get(self.published_post.get_absolute_url())
        self.assertContains(response, older.get_absolute_url())
        self.assertContains(response, newer.get_absolute_url())
        self.assertNotContains(response, draft_between.get_absolute_url())
        self.assertContains(response, reverse("blog:archive"))

        response = self.client.get(newer.get_absolute_url())
        self.assertEqual(response.context["newer_post"], None)
        self.assertEqual(response.context["older_post"], self.published_post)

        response = self.client.get(older.get_absolute_url())
        self.assertEqual(response.context["older_post"], None)
        self.assertEqual(response.context["newer_post"], self.published_post)

    def test_detail_neighbours_break_ties_on_same_timestamp(self):
        # The factory stamps every post with the same date, so the ordering
        # must fall back to something deterministic instead of skipping posts.
        same_time = BlogPostFactory(publish=True, date_published=self.published_post.date_published)
        response = self.client.get(same_time.get_absolute_url())
        self.assertEqual(response.context["older_post"], self.published_post)
        response = self.client.get(self.published_post.get_absolute_url())
        self.assertEqual(response.context["newer_post"], same_time)
