"""Current-avatar file-store tests."""

from pathlib import Path

from telegram_monitor_scraper.avatar_storage import ChannelAvatarStorage


async def test_storage_replaces_and_deletes_a_channel_avatar(tmp_path: Path) -> None:
    storage = ChannelAvatarStorage(tmp_path)

    await storage.save(1, b"first")
    await storage.save(1, b"second")

    assert storage.path_for(1).read_bytes() == b"second"
    await storage.delete(1)
    assert not storage.path_for(1).exists()
