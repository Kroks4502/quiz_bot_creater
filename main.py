import asyncio
import os
import platform
import random
from asyncio import sleep
from pathlib import Path

import yaml
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPoll, Poll, PollAnswer, PollAnswerVoters, PollResults, TextWithEntities

QUIZ_BOT = "QuizBot"
SRC_DIR = Path("sources")


class Waiter:
    def __init__(self, client: TelegramClient, expected: str = None):
        self.client = client
        self.expected = expected
        self.event = events.NewMessage(chats=QUIZ_BOT)
        self.is_get_answer = False

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

        self.client.remove_event_handler(self.wait_answer, self.event)


async def create_quiz(client: TelegramClient, file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Отменяем текущее состояние бота
    async with Waiter(client):
        await client.send_message(QUIZ_BOT, "/cancel")

    # Создаем новый
    async with Waiter(client, "Вы решили создать новый тест"):
        await client.send_message(QUIZ_BOT, "/newquiz")

    # Отправляем название
    async with Waiter(client, "пришлите описание"):
        await client.send_message(QUIZ_BOT, data["quiz_title"])

    # Отправляем описание или пропускаем
    async with Waiter(client, "Отправьте мне первый вопрос"):
        if data["quiz_desc"]:
            await client.send_message(QUIZ_BOT, data["quiz_desc"])
        else:
            await client.send_message(QUIZ_BOT, "/skip")

    # Отправляем вопросы
    for question in data["questions"]:
        title = question["title"]
        correct_answer = question["correct_answer"]
        incorrect_answers = question["incorrect_answers"]

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
                    results=PollResults(results=[PollAnswerVoters(option=bytes(1), voters=200_000, correct=True)]),
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
        for file in os.listdir(SRC_DIR):
            if not file.endswith(".yml") or not os.path.isfile(SRC_DIR / file):
                continue
            await create_quiz(client, SRC_DIR / file)


if __name__ == "__main__":
    asyncio.run(main())
