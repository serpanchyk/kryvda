# Golden studio — локальна розмітка

Experimental UI для одного анотатора. PostgreSQL слугує лише джерелом Post Revisions:
усі запити виконуються в read-only транзакціях. Немає нових production таблиць чи API.

## Запуск

1. Залиште наявний PostgreSQL зі збором постів запущеним.
2. За потреби скопіюйте `.env.example` у `.env` у цій директорії та вкажіть фактичний DSN.
   Зазвичай це не потрібно: launcher підключається до сервісу `postgres` через наявну мережу
   основного Compose-проєкту. Для віддаленого сервера вкажіть його адресу.
3. Із кореня репозиторію виконайте:

```bash
uv run python experiments/annotation-ui/src/launch_editor.py
```

Launcher автоматично читає існуючі PostgreSQL settings з кореневої `.env` та
`infra/postgres/.env`, якщо experimental DSN не заданий. Поточний Unix UID/GID передається
контейнеру, щоб створені анотації належали вам.

Відкрийте http://localhost:8090. Compose є незалежним experimental stack і не запускає
production frontend чи API. Сторінка доступна лише на loopback хоста. Інструмент не має
авторизації; не публікуйте його через reverse proxy. Запускайте один екземпляр backend.

## Розмітка

- Знайдіть пости за текстом, каналом і датою. Пошук є буквальним, без regex чи SQL wildcard.
- Оберіть пост: редактор збереже snapshot конкретної ревізії та ID прикладу.
- Заповніть причину відбору й особливості прикладу. Для хибного keyword-збігу увімкніть
  відповідний прапорець і залиште семантичні секції порожніми.
- Виділіть фразу у вихідному тексті, додайте сутність, твердження або риторичну ознаку.
  Кнопка «Використати виділення» заповнює доказ автоматично. Можна додати кілька доказів.
- Авторів і цілі обирайте з уже створених сутностей. Canonical entity можна обрати з локального
  довідника або створити як candidate. Невизначені згадки мають порожні canonical fields.
- Чернетки зберігаються після паузи у введенні. Статус угорі підтверджує збереження;
  не закривайте сторінку, доки воно триває. Конфлікт версії потребує перезавантаження.
- «Завершити й перейти далі» перевіряє схему та посилання. Помилки залишають форму відкритою.
  «Мої чернетки й готові» дозволяє повернутися до попередніх прикладів навіть без PostgreSQL.
- Вкладка `JSON` може прискорити розмітку через ChatGPT: «Скопіювати пакет для ChatGPT» копіює
  незмінний post і `annotation_import_schema_v1` лише для mutable `selection` та `annotations`.
  Вставте відповідь (можна в одному ```json fenced block) і натисніть «Перевірити та відкрити
  preview». На цьому кроці нічого не записується: перегляньте та за потреби виправте результат у
  формі, а потім підтвердьте збереження. Лише тоді нові canonical names створюються як local
  candidate entries; точні наявні canonical name + entity type перевикористовуються.

## Файли й відновлення

Усі дані зберігаються в bind-mounted `experiments/datasets/golden_v0/data/`:

- `editor.json` — джерело відновлення чернеток, snapshot-ів, статусів і локального registry;
- `annotations.jsonl` — лише завершені записи зі схемою annotation_schema_v1;
- `selection_manifest.jsonl` — ID, source та причина відбору завершених записів;
- `entity_registry.jsonl` — локальні canonical IDs, назви, aliases, типи й статуси.

Кожен файл замінюється атомарно; стан редактора записується першим. Наступне збереження
відновлює експорти зі стану, якщо робота перервалася між записами. Не редагуйте exports вручну
при активному редакторі: він відтворює їх зі свого стану. До першого запуску наявні завершені
анотації імпортуються автоматично. Жодних LLM-викликів чи автоматичної розмітки немає.

Після сесії зупиніть редактор перед створенням узгодженого DVC snapshot:

```bash
docker stop annotation-ui-annotation-ui-1
uv run python experiments/datasets/golden_v0/src/golden_v0_validation.py
uv run dvc add experiments/datasets/golden_v0/data
uv run dvc status
git add experiments/datasets/golden_v0/data.dvc
git commit -m "data: update golden pilot annotations"
```

Без налаштованого DVC remote cache існує лише локально; Git pointer сам по собі не містить даних.
UI ніколи не запускає Git/DVC-команди. Production registry та його міграція — майбутня задача.

## Перевірки

`uv run pytest` включає backend тести. Для frontend у `web/` виконайте `npm ci`,
`npm run lint`, `npm test`, `npm run build`. Вони незалежні від production frontend.
