"""Explicit topic choices for the search form."""
TOPICS = ['logement', 'transports', 'énergie', 'emploi', 'éducation',
          'environnement', 'santé', 'animaux']


def topic_options(extra=()):
    return list(dict.fromkeys([*TOPICS, *extra]))


class TopicSelectionError(ValueError):
    """A short validation message safe to display next to the search form."""


def parse_topics(selected, free_text):
    """Combine pills and comma-separated free topics before any collection."""
    if not isinstance(selected, list) or not isinstance(free_text, str):
        raise TopicSelectionError('Choisis des sujets ou écris-les dans la ligne de recherche.')
    topics, seen = [], set()
    for raw in [*selected, *free_text.split(',')]:
        if not isinstance(raw, str):
            raise TopicSelectionError('Chaque sujet doit être du texte.')
        topic = raw.strip()
        if not topic:
            continue
        if (not 3 <= len(topic) <= 100
                or any(ord(char) < 32 or ord(char) == 127 for char in topic)
                or not any(char.isalnum() for char in topic)):
            raise TopicSelectionError('Chaque sujet doit contenir de 3 à 100 caractères.')
        if topic.casefold() not in seen:
            topics.append(topic)
            seen.add(topic.casefold())
    if not 1 <= len(topics) <= 8:
        raise TopicSelectionError('Choisis ou écris de 1 à 8 sujets.')
    return topics
