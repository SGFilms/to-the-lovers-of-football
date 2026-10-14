"""Картинка-обложка приветствия."""

import logging
from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parent.parent / "assets"
COVER = ASSETS / "cover.png"
AVATAR = ASSETS / "avatar.png"

# После первой отправки Telegram выдаёт file_id, и картинку больше не нужно загружать.
_cover_file_id: str | None = None


async def send_with_cover(message: Message, caption: str, markup: InlineKeyboardMarkup) -> None:
    global _cover_file_id
    if not COVER.exists():
        await message.answer(caption, reply_markup=markup)
        return
    sent = await message.answer_photo(
        _cover_file_id or FSInputFile(COVER), caption=caption, reply_markup=markup
    )
    if sent.photo:
        _cover_file_id = sent.photo[-1].file_id
