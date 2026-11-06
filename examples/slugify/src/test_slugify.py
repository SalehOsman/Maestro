import unittest
from slugify import slugify


class TestSlugify(unittest.TestCase):
    def test_slugify_basic_formatting(self):
        """Lowercase; runs of spaces, punctuation, underscores become single '-'; no leading/trailing '-'."""
        self.assertEqual(slugify("  Hello, World!  "), "hello-world")
        self.assertEqual(slugify("Multiple---Spaces   and..Punctuation"), "multiple-spaces-and-punctuation")
        self.assertEqual(slugify("test__slug--example"), "test-slug-example")
        self.assertEqual(slugify("Hello  -  World"), "hello-world")

    def test_slugify_multilingual_and_unicode_scripts(self):
        """Letters and digits from any script are kept (including Arabic)."""
        self.assertEqual(slugify("مرحبا بالعالم 2"), "مرحبا-بالعالم-2")
        self.assertEqual(slugify("Café & Restaurant 123"), "café-restaurant-123")
        self.assertEqual(slugify("Привет, мир! 42"), "привет-мир-42")

    def test_slugify_unicode_combining_marks(self):
        """Unicode combining marks (such as Arabic tanween and harakat) are preserved."""
        self.assertEqual(slugify("مرحباً بك"), "مرحباً-بك")

    def test_slugify_empty_or_punctuation_only_raises_value_error(self):
        """Empty string or strings containing only spaces/punctuation raise ValueError."""
        with self.assertRaises(ValueError):
            slugify("")
        with self.assertRaises(ValueError):
            slugify("!!!")
        with self.assertRaises(ValueError):
            slugify("---")
        with self.assertRaises(ValueError):
            slugify("   ")
        with self.assertRaises(ValueError):
            slugify(" - _ - ")

    def test_slugify_non_string_argument_raises_type_error(self):
        """Non-string inputs raise TypeError."""
        for invalid_input in [None, 123, 45.6, [], {}, True]:
            with self.subTest(input=invalid_input):
                with self.assertRaises(TypeError):
                    slugify(invalid_input)


if __name__ == "__main__":
    unittest.main()
