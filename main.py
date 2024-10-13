import asyncio
import os
import platform
import random
from asyncio import sleep
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, constr
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPoll, Poll, PollAnswer, PollAnswerVoters, PollResults, TextWithEntities

QUIZ_BOT = "QuizBot"
QUIZ_SRC_DIR = Path("sources")
QUIZ_FILEPATH = QUIZ_SRC_DIR / "example.yml"
ONLY_CHECK = False


class Question(BaseModel):
    title: str = Field(min_length=1, max_length=2000)
    incorrect_answers: list[constr(min_length=1, max_length=100)] = Field(max_length=9)
    correct_answer: str = Field(min_length=1, max_length=100)
    solution: str | None = Field(None, min_length=1, max_length=200)


class Quiz(BaseModel):
    quiz_title: str = Field(min_length=1, max_length=128)
    quiz_desc: str | None = Field(None, min_length=1, max_length=1024)
    questions: list[Question]


class Waiter:
    TIMEOUT = 5

    def __init__(self, client: TelegramClient, expected: str = None):
        self.client = client
        self.expected = expected
        self.event = events.NewMessage(chats=QUIZ_BOT)
        self.is_get_answer = False
        self.start_ts = datetime.now().timestamp()

        async def wait_answer(event: events.NewMessage.Event):
            self.is_get_answer = True
            if self.expected and self.expected.lower() not in event.message.message.lower():
                raise ValueError(f"Ответ {event.message.message} не соответствует ожидаемому: {self.expected.lower()}.")

        self.wait_answer = wait_answer

    async def __aenter__(self):
        self.client.add_event_handler(self.wait_answer, self.event)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        while not self.is_get_answer:
            await sleep(0.5)
            if datetime.now().timestamp() - self.start_ts > self.TIMEOUT:
                raise TimeoutError(
                    f"Время ожидания ответа бота превысило {self.TIMEOUT} секунд. Ожидаемый ответ {self.expected}"
                )

        self.client.remove_event_handler(self.wait_answer, self.event)


async def create_quiz(client: TelegramClient, quiz: Quiz):
    # Отменяем текущее состояние бота
    async with Waiter(client):
        await client.send_message(QUIZ_BOT, "/cancel")

    # Создаем новый
    async with Waiter(client, "Вы решили создать новый тест"):
        await client.send_message(QUIZ_BOT, "/newquiz")

    # Отправляем название
    async with Waiter(client, "пришлите описание"):
        await client.send_message(QUIZ_BOT, quiz.quiz_title)

    # Отправляем описание или пропускаем
    async with Waiter(client, "Отправьте мне первый вопрос"):
        if quiz.quiz_desc:
            await client.send_message(QUIZ_BOT, quiz.quiz_desc)
        else:
            await client.send_message(QUIZ_BOT, "/skip")

    # Отправляем вопросы
    for question in quiz.questions:
        if len(question.title) > 256:
            title = "Выберите ответ"
            message = question.title
        else:
            title = question.title
            message = None
        correct_answer = question.correct_answer
        incorrect_answers = question.incorrect_answers

        if message:
            # Отправляем сообщение перед формой poll
            async with Waiter(client, "будет показываться после этого сообщения"):
                await client.send_message(QUIZ_BOT, message)

        # Отправляем форму poll
        async with Waiter(client, "Теперь отправьте следующий"):
            await client.send_message(
                QUIZ_BOT,
                file=MessageMediaPoll(
                    poll=Poll(
                        id=random.randint(0, 100_000),
                        question=TextWithEntities(title, entities=[]),
                        answers=[
                            PollAnswer(TextWithEntities(text, entities=[]), bytes(idx))
                            for idx, text in enumerate([correct_answer, *incorrect_answers], start=1)
                        ],
                        quiz=True,
                    ),
                    results=PollResults(
                        results=[PollAnswerVoters(option=bytes(1), voters=200_000, correct=True)],
                        solution=question.solution,
                        solution_entities=[] if question.solution else None,
                    ),
                ),
            )

    # Публикуем
    async with Waiter(client, "Укажите ограничение времени"):
        await client.send_message(QUIZ_BOT, "/done")

    # Указываем ограничение времени
    async with Waiter(client, "в случайном порядке"):
        await client.send_message(QUIZ_BOT, "30 сек")

    # Указываем опцию ("Перемешать всё", "По порядку", "Только вопросы", "Только ответы")
    await client.send_message(QUIZ_BOT, "Только ответы")

    await sleep(1)

    message = await client.get_messages(QUIZ_BOT, limit=1)

    print(message[-1].message)


async def main():
    load_dotenv(Path(__file__).parent / ".env")

    client: TelegramClient = TelegramClient(
        session="quiz_bot_creator",
        api_id=int(os.getenv("API_ID")),
        api_hash=os.getenv("API_HASH"),
        auto_reconnect=True,
        device_model=f"{platform.python_implementation()} {platform.python_version()}",
        system_version=f"{platform.system()} {platform.release()}",
        app_version="quiz_creator",
    )

    async with client:
        with open(QUIZ_FILEPATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        quiz = Quiz(**data)

        if not ONLY_CHECK:
            await create_quiz(client, quiz)


if __name__ == "__main__":
    asyncio.run(main())
