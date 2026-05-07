from aiogram import F, Router
from aiogram.types import Message

router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def echo(message: Message) -> None:
    if message.text is None:
        return
    await message.answer(message.text)
