"""The conversation with the AI manager, living in the session.

Neither `Conversation` nor `Message`: what bounds a single conversation — a business
centre, an employee, a working day — is unknown right now, and a model would fix the
answer before it appears. The session keeps the conversation for exactly as long as the
sign-in lasts, and survives moving from one BC to another — precisely the behaviour
checked at this stage.

Messages are stored as dicts, because the session is serialised to JSON.
"""

SESSION_KEY = "assistant_conversation"

# One reply to every question: no model is called, search over the passport is the next stage.
CANNED_REPLY = (
    "Пока я не подключён к данным паспорта — отвечаю заглушкой. "
    "Полноценные ответы появятся на следующем этапе."
)


def history(session) -> list[dict]:
    """The whole conversation — what the panel shows when a screen opens."""
    return session.get(SESSION_KEY, [])


def ask(session, question: str) -> list[dict]:
    """Records the question with its answer and returns the whole conversation.

    The whole one, not a single pair: the panel gets both its first render on the page and
    its update after sending from this same value, so it is built by the same code.
    """
    question = question.strip()
    if not question:
        # An empty send does not change the conversation: a bubble without text has nothing to answer.
        return history(session)

    conversation = history(session) + [
        {"role": "question", "text": question},
        {"role": "answer", "text": CANNED_REPLY},
    ]
    session[SESSION_KEY] = conversation
    return conversation
