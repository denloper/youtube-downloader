from messenger_ai.schemas import IncomingMessage


async def test_report_contains_channel_stats_and_can_be_delivered(runtime):
    await runtime.pipeline.handle(
        IncomingMessage(
            channel="telegram",
            chat_id="1",
            sender_id="1",
            sender_name="Аня",
            text="Привет",
            message_id="1",
        )
    )
    await runtime.pipeline.handle(
        IncomingMessage(
            channel="whatsapp",
            chat_id="2",
            sender_id="2",
            sender_name="Олег",
            text="Хочу возврат денег",
            message_id="2",
        )
    )
    stats = await runtime.reports.collect_stats()
    assert stats["inbound"] == 2
    assert stats["by_channel"]["telegram"] == 1
    assert stats["by_channel"]["whatsapp"] == 1
    assert stats["escalated"] >= 1
    report = await runtime.reports.build_report(deliver=True)
    assert "Отчёт" in report.title
    assert "Telegram" in report.body_text
    assert "WhatsApp" in report.body_text
    assert runtime.adapters["telegram"].owner_messages
    short = await runtime.reports.short_stats()
    assert "Статистика" in short
