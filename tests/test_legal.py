from decimal import Decimal

from lflbot.legal import NOT_SET, Seller, format_amount, offer_text, privacy_text

TELEGRAM_LIMIT = 4096
LONG_SELLER = Seller(
    name="Константинопольский Александр Владимирович",
    inn="123456789012",
    email="very.long.contact.address@example.com",
)


def test_texts_fit_in_one_telegram_message() -> None:
    assert len(offer_text(LONG_SELLER, Decimal("1499.99"), 365)) < TELEGRAM_LIMIT
    assert len(privacy_text(LONG_SELLER)) < TELEGRAM_LIMIT


def test_offer_has_seller_price_and_days() -> None:
    text = offer_text(LONG_SELLER, Decimal("1.00"), 30)
    assert LONG_SELLER.name in text
    assert "ИНН 123456789012" in text
    assert "1 ₽ за 30 дней" in text
    assert LONG_SELLER.email in text


def test_missing_seller_details_are_marked_and_html_is_escaped() -> None:
    text = privacy_text(Seller(name="<Иван>", inn="", email=""))
    assert "&lt;Иван&gt;" in text
    assert f"ИНН {NOT_SET}" in text


def test_format_amount() -> None:
    assert format_amount(Decimal("1.00")) == "1"
    assert format_amount(Decimal("149.5")) == "149,50"
