from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SetMyCommands

from lflbot.bot import BOT_COMMANDS, texts
from lflbot.bot.profile import apply_profile
from tests.tg import make_settings

SETTINGS = make_settings()


def fake_bot(*, description: str = "", photos: int = 0) -> AsyncMock:
    bot = AsyncMock()
    bot.get_my_description.return_value = SimpleNamespace(description=description)
    bot.get_my_short_description.return_value = SimpleNamespace(short_description="")
    bot.get_me.return_value = SimpleNamespace(id=100)
    bot.get_user_profile_photos.return_value = SimpleNamespace(total_count=photos)
    return bot


def test_descriptions_fit_telegram_limits() -> None:
    assert len(texts.BOT_SHORT_DESCRIPTION.format(price="1499,99", days=365)) <= 120
    assert len(texts.BOT_DESCRIPTION.format(price="1499,99", days=365)) <= 512


async def test_sets_profile_and_avatar_when_missing() -> None:
    bot = fake_bot()
    await apply_profile(bot, SETTINGS)

    bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    bot.set_my_description.assert_awaited_once_with(
        texts.BOT_DESCRIPTION.format(price="1", days=30)
    )
    bot.set_my_short_description.assert_awaited_once()
    bot.set_my_profile_photo.assert_awaited_once()


async def test_keeps_existing_avatar_and_unchanged_description() -> None:
    bot = fake_bot(description=texts.BOT_DESCRIPTION.format(price="1", days=30), photos=1)
    await apply_profile(bot, SETTINGS)
    bot.set_my_description.assert_not_awaited()
    bot.set_my_profile_photo.assert_not_awaited()


async def test_telegram_errors_do_not_stop_the_bot() -> None:
    bot = fake_bot()
    bot.set_my_commands.side_effect = TelegramNetworkError(
        method=SetMyCommands(commands=[]), message="timeout"
    )
    await apply_profile(bot, SETTINGS)
