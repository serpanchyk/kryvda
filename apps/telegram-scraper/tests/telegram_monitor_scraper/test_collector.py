"""Collection orchestration tests without a Telegram gateway or PostgreSQL runtime."""

from datetime import UTC, datetime, timedelta

from telegram_monitor_scraper.collector import Collector
from telegram_monitor_scraper.models import (
    ChannelAvatar,
    ChannelFetchRequest,
    ChannelFetchResult,
    GatewayRateLimitedError,
    MonitoredChannel,
    TelegramPost,
)


class FakeRepository:
    def __init__(self, channels: list[MonitoredChannel] | None = None) -> None:
        self.channels = channels or [MonitoredChannel(1, "example_channel", 1, "public")]
        self.live_cursor = 0
        self.backfill_cursor: int | None = None
        self.complete = False
        self.cursor_exists = True
        self.persisted: list[tuple[int, str]] = []
        self.identities: list[tuple[int, int, str | None, str | None]] = []
        self.avatar_updates: list[tuple[int, str]] = []
        self.cleared_avatars: list[int] = []
        self.errors: list[str] = []
        self.successes: list[tuple[int, bool]] = []

    async def active_channels(self) -> list[MonitoredChannel]:
        return self.channels

    async def latest_message_id(self, channel_id: int) -> int:
        return self.live_cursor

    async def live_cursor_exists(self, channel_id: int) -> bool:
        return self.cursor_exists

    async def update_channel_identity(
        self, channel_id: int, peer_id: int, username: str | None, title: str | None
    ) -> None:
        self.identities.append((channel_id, peer_id, username, title))

    async def backfill_before_message_id(self, channel_id: int) -> int | None:
        return self.backfill_cursor

    async def update_channel_avatar(self, channel_id: int, content_type: str) -> None:
        self.avatar_updates.append((channel_id, content_type))

    async def clear_channel_avatar(self, channel_id: int) -> None:
        self.cleared_avatars.append(channel_id)

    async def backfill_complete(self, channel_id: int) -> bool:
        return self.complete

    async def persist_post(
        self, channel: MonitoredChannel, post: TelegramPost, priority: str
    ) -> bool:
        self.persisted.append((post.message_id, priority))
        return True

    async def advance_live_cursor(self, channel_id: int, message_id: int) -> None:
        self.cursor_exists = True
        self.live_cursor = message_id

    async def advance_backfill_cursor(
        self, channel_id: int, message_id: int | None, complete: bool
    ) -> None:
        self.backfill_cursor = message_id
        self.complete = complete

    async def record_success(self, channel_id: int, clear_error: bool = True) -> None:
        self.successes.append((channel_id, clear_error))

    async def record_error(self, channel_id: int, message: str) -> None:
        self.errors.append(message)


class FakeGateway:
    """Page through in-memory posts with the gateway's cursor semantics."""

    def __init__(
        self,
        live: list[TelegramPost],
        historical: list[TelegramPost],
        page_size: int = 100,
        avatar: ChannelAvatar | None = ChannelAvatar(b"\xff\xd8\xffavatar", "image/jpeg"),
        avatar_error: str | None = None,
    ) -> None:
        self.live = live
        self.historical = sorted(historical, key=lambda item: item.message_id, reverse=True)
        self.page_size = page_size
        self.avatar = avatar
        self.avatar_error = avatar_error
        self.requests: list[ChannelFetchRequest] = []

    async def fetch(
        self, channel: MonitoredChannel, request: ChannelFetchRequest
    ) -> ChannelFetchResult:
        self.requests.append(request)
        head: int | None = None
        newer: list[TelegramPost] = []
        if request.live_after_message_id is None:
            head = 100
        else:
            newer = [p for p in self.live if p.message_id > request.live_after_message_id]
            newer = newer[: self.page_size]
        older: list[TelegramPost] = []
        backfill_complete = True
        if request.backfill is not None:
            before = request.backfill.before_message_id
            candidates = [p for p in self.historical if before is None or p.message_id < before]
            page = candidates[: self.page_size]
            reached_cutoff = False
            for post in page:
                if post.published_at < request.backfill.not_before:
                    reached_cutoff = True
                    break
                older.append(post)
            backfill_complete = reached_cutoff or len(page) < self.page_size
        return ChannelFetchResult(
            peer_id=1,
            username="example_channel",
            title="Example",
            avatar=self.avatar if request.include_avatar else None,
            avatar_error=self.avatar_error if request.include_avatar else None,
            head_message_id=head,
            newer_posts=newer,
            newer_complete=len(newer) < self.page_size,
            older_posts=older,
            backfill_complete=backfill_complete,
        )


class FakeAvatarStorage:
    def __init__(self) -> None:
        self.saved: list[tuple[int, bytes]] = []
        self.deleted: list[int] = []

    async def save(self, channel_id: int, content: bytes) -> None:
        self.saved.append((channel_id, content))

    async def delete(self, channel_id: int) -> None:
        self.deleted.append(channel_id)


def post(message_id: int, days_old: int = 0) -> TelegramPost:
    return TelegramPost(
        message_id=message_id,
        published_at=datetime.now(UTC) - timedelta(days=days_old),
        content="content",
        edited_at=None,
        metadata={},
        attachments=[],
    )


async def test_live_posts_are_collected_before_backfill() -> None:
    repository = FakeRepository()
    storage = FakeAvatarStorage()
    collector = Collector(
        repository,
        FakeGateway([post(20)], [post(10), post(9, 366)]),
        storage,  # type: ignore[arg-type]
    )

    await collector.collect_once()

    assert repository.persisted == [(20, "live"), (10, "backfill")]
    assert repository.identities == [(1, 1, "example_channel", "Example")]
    assert repository.avatar_updates == [(1, "image/jpeg")]
    assert storage.saved == [(1, b"\xff\xd8\xffavatar")]
    assert repository.complete is True
    assert repository.live_cursor == 20
    assert repository.successes == [(1, True)]


async def test_new_channel_sets_live_cursor_before_collecting_history() -> None:
    repository = FakeRepository()
    repository.cursor_exists = False
    gateway = FakeGateway([post(20)], [post(10), post(9, 366)])
    collector = Collector(repository, gateway, FakeAvatarStorage())  # type: ignore[arg-type]

    await collector.collect_once()

    assert gateway.requests[0].live_after_message_id is None
    assert repository.live_cursor == 100
    assert repository.persisted == [(10, "backfill")]


async def test_history_is_paged_within_the_per_run_budget() -> None:
    repository = FakeRepository()
    gateway = FakeGateway([], [post(message_id) for message_id in range(1, 11)], page_size=3)
    collector = Collector(
        repository,
        gateway,
        FakeAvatarStorage(),  # type: ignore[arg-type]
        max_pages_per_channel=2,
    )

    await collector.collect_once()

    assert [message_id for message_id, _ in repository.persisted] == [10, 9, 8, 7, 6, 5]
    assert repository.backfill_cursor == 5
    assert repository.complete is False
    assert [request.include_avatar for request in gateway.requests] == [True, False]

    await Collector(repository, gateway, FakeAvatarStorage()).collect_once()  # type: ignore[arg-type]

    assert [message_id for message_id, _ in repository.persisted][-4:] == [4, 3, 2, 1]
    assert repository.complete is True


async def test_live_backlog_is_caught_up_across_pages() -> None:
    repository = FakeRepository()
    repository.complete = True
    gateway = FakeGateway([post(message_id) for message_id in range(1, 6)], [], page_size=2)
    collector = Collector(repository, gateway, FakeAvatarStorage())  # type: ignore[arg-type]

    await collector.collect_once()

    assert repository.persisted == [(message_id, "live") for message_id in range(1, 6)]
    assert all(request.backfill is None for request in gateway.requests)
    assert len(gateway.requests) == 3


async def test_missing_avatar_clears_storage_and_metadata() -> None:
    repository = FakeRepository()
    storage = FakeAvatarStorage()
    collector = Collector(
        repository,
        FakeGateway([], [], avatar=None),
        storage,  # type: ignore[arg-type]
    )

    await collector.collect_once()

    assert storage.deleted == [1]
    assert repository.cleared_avatars == [1]


async def test_avatar_error_does_not_block_post_collection() -> None:
    repository = FakeRepository()
    collector = Collector(
        repository,
        FakeGateway([post(20)], [], avatar=None, avatar_error="avatar download failed"),
        FakeAvatarStorage(),  # type: ignore[arg-type]
    )

    await collector.collect_once()

    assert repository.persisted == [(20, "live")]
    assert repository.errors == ["avatar download failed"]
    assert repository.successes == [(1, False)]


async def test_avatar_storage_failure_is_recorded() -> None:
    class FailingStorage(FakeAvatarStorage):
        async def save(self, channel_id: int, content: bytes) -> None:
            raise OSError("disk full")

    repository = FakeRepository()
    collector = Collector(
        repository,
        FakeGateway([post(20)], []),
        FailingStorage(),  # type: ignore[arg-type]
    )

    await collector.collect_once()

    assert repository.persisted == [(20, "live")]
    assert repository.errors == ["disk full"]


async def test_gateway_failure_is_recorded_per_channel() -> None:
    class FailingGateway(FakeGateway):
        async def fetch(
            self, channel: MonitoredChannel, request: ChannelFetchRequest
        ) -> ChannelFetchResult:
            if channel.id == 1:
                raise RuntimeError("gateway unavailable")
            return await super().fetch(channel, request)

    repository = FakeRepository(
        [
            MonitoredChannel(1, "first", 1, "public"),
            MonitoredChannel(2, "second", 2, "public"),
        ]
    )
    collector = Collector(
        repository,
        FailingGateway([post(20)], []),
        FakeAvatarStorage(),  # type: ignore[arg-type]
    )

    await collector.collect_once()

    assert repository.errors == ["gateway unavailable"]
    assert repository.successes == [(2, True)]


async def test_rate_limit_stops_the_whole_run() -> None:
    class LimitedGateway(FakeGateway):
        async def fetch(
            self, channel: MonitoredChannel, request: ChannelFetchRequest
        ) -> ChannelFetchResult:
            raise GatewayRateLimitedError("Telegram gateway rate limited", 600)

    repository = FakeRepository(
        [
            MonitoredChannel(1, "first", 1, "public"),
            MonitoredChannel(2, "second", 2, "public"),
        ]
    )
    gateway = LimitedGateway([], [])
    collector = Collector(repository, gateway, FakeAvatarStorage())  # type: ignore[arg-type]

    await collector.collect_once()

    assert repository.errors == ["Telegram gateway rate limited"]
    assert len(gateway.requests) == 0
    assert repository.successes == []
