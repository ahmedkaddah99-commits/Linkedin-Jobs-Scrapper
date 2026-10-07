"""Local Argos translation before Nemo; original evidence is never replaced."""
from functools import lru_cache
from threading import Lock

TRANSLATION_LOCK = Lock()


def source_language(text):
    from langdetect import DetectorFactory, detect
    DetectorFactory.seed = 0
    return detect(text)


@lru_cache(maxsize=4096)
def translate_text(text, language):
    from argostranslate import translate
    with TRANSLATION_LOCK:
        languages = {item.code: item for item in translate.get_installed_languages()}
        if language not in languages or 'en' not in languages:
            raise ValueError('translation_model_missing_' + language)
        translator = languages[language].get_translation(languages['en'])
        if translator is None:
            raise ValueError('translation_model_missing_' + language)
        return translator.translate(text)


def english_passages(passages):
    language = source_language('\n'.join(p['text'] for p in passages))
    if language == 'en':
        return passages
    return [{**p, 'original_text': p['text'], 'text': translate_text(p['text'], language)} for p in passages]
