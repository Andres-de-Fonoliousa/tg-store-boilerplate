from app.config import settings

if settings.LANG == "en":
    from app.i18n.en import MESSAGES
else:
    from app.i18n.ar import MESSAGES


def t(key: str, **kwargs) -> str:
    template = MESSAGES.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
