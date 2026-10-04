"""The one exception the topic tools raise on purpose."""


class TopicError(ValueError):
    """A topic-model request can't be met: an unknown model or topic, too little text, books that
    changed since the model was fitted… The message is meant for the user and is shown as is."""
