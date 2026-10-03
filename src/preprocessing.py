"""Conservative, configurable normalization; NOT Vietnamese word segmentation."""
from dataclasses import asdict, dataclass
import re
import unicodedata

# Deliberately small: ambiguous forms (e.g. 'k', 'đc', 'm', 't') stay untouched.
TEENCODE = {"ko": "không", "khong": "không", "hok": "không", "dc": "được"}
URL = re.compile(r"(?:https?://|www\.)[^\s<>]+", re.IGNORECASE)
MENTION = re.compile(r"(?<!\w)@[\w.]+", re.UNICODE)
TOKEN = re.compile(r"\b\w+\b", re.UNICODE)


@dataclass(frozen=True)
class PreprocessingConfig:
    lowercase: bool = False
    normalize_teencode: bool = False
    mask_urls: bool = True
    mask_mentions: bool = True
    strip_hashtag_marker: bool = True

    def to_dict(self):
        return asdict(self)


def preprocess_text(text: str, config: PreprocessingConfig | None = None) -> str:
    """Preserve emoji, emoticons, accents, numbers and punctuation as model signals.

    Lowercasing and dictionary normalization are opt-in ablations. Invalid input
    raises rather than silently converting missing values into the word 'nan'.
    URLs/mentions use ordinary text placeholders; they are not special tokens.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string; handle missing values in the data pipeline")
    config = config or PreprocessingConfig()
    text = unicodedata.normalize("NFC", text)
    # Remove invisible word-boundary artifacts, retain emoji ZWJ and variation selectors.
    text = text.replace("\u200b", " ").replace("\ufeff", "")
    if config.mask_urls:
        text = URL.sub(" urltoken ", text)
    if config.mask_mentions:
        text = MENTION.sub(" usertoken ", text)
    if config.strip_hashtag_marker:
        text = re.sub(r"(?<!\w)#(?=\w)", "", text)
    if config.lowercase:
        text = text.lower()
    if config.normalize_teencode:
        text = TOKEN.sub(lambda match: TEENCODE.get(match[0].lower(), match[0]), text)
    return " ".join(text.split())
