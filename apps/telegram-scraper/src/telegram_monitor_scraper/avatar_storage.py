"""Persist current channel avatars outside PostgreSQL.

The scraper owns writes to the shared avatar volume. PostgreSQL records only the API URL and
content type needed for the API to expose the current image.
"""

import asyncio
from pathlib import Path


class ChannelAvatarStorage:
    """Store one current avatar per monitored channel.

    Args:
        directory: Shared directory mounted by the scraper and API services.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def save(self, channel_id: int, content: bytes) -> None:
        """Write an avatar atomically for a monitored channel.

        Args:
            channel_id: Internal monitored-channel identifier.
            content: Complete profile-image payload downloaded from Telegram.
        """
        await asyncio.to_thread(self._write, channel_id, content)

    async def delete(self, channel_id: int) -> None:
        """Remove a channel's current avatar if one is stored.

        Args:
            channel_id: Internal monitored-channel identifier.
        """
        await asyncio.to_thread(self._delete, channel_id)

    def path_for(self, channel_id: int) -> Path:
        """Return the deterministic path assigned to a channel avatar.

        Args:
            channel_id: Internal monitored-channel identifier.

        Returns:
            Path that may contain the channel's current avatar.
        """
        return self._directory / f"{channel_id}.avatar"

    def _write(self, channel_id: int, content: bytes) -> None:
        """Replace an avatar without exposing a partial file to API readers."""
        self._directory.mkdir(parents=True, exist_ok=True)
        destination = self.path_for(channel_id)
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)

    def _delete(self, channel_id: int) -> None:
        """Remove the deterministic avatar path when it exists."""
        self.path_for(channel_id).unlink(missing_ok=True)
