AUTHOR = "Jannik Glückert"
SITENAME = "EBADBLOG"
SITESUBTITLE = "A blog about weirdly named POSIX error codes and more"
SITEURL = ""
HEADER_COVER = "images/errno.jpg"

THEME = "theme/pelican-clean-blog"

PATH = "content"

TIMEZONE = "Europe/Berlin"

DEFAULT_LANG = "en"

COLOR_SCHEME_CSS = "monokai.css"
CSS_OVERRIDE = "css/custom.css"
DISABLE_CUSTOM_THEME_JAVASCRIPT = True

FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

SOCIAL = (("github", "https://github.com/Jannik2099"),)

DEFAULT_PAGINATION = 10

STATIC_PATHS = ["css", "images"]

MARKDOWN = {
    "extension_configs": {
        "markdown.extensions.extra": {},
        "markdown.extensions.meta": {},
        "markdown.extensions.codehilite": {
            "guess_lang": "false",
            "css_class": "highlight",
        },
    },
    "output_format": "html5",
}

SLUG_REGEX_SUBSTITUTIONS = [
    (r"[^\w\s+-]", ""),  # remove non-alphabetical/whitespace/'+-' chars
    (r"(?u)\A\s*", ""),  # strip leading whitespace
    (r"(?u)\s*\Z", ""),  # strip trailing whitespace
    (r"[\s]+", "-"),  # reduce multiple whitespace to single '-'
]
