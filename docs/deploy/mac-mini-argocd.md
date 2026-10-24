# Кривда на кластері Mac mini

Стан перевірки 2026-10-16: три Linux/amd64 вузли, K3s, Traefik, Argo CD,
Sealed Secrets у kube-system, StorageClass local-path (WaitForFirstConsumer).
Kubernetes доповнює звичайний Docker Compose deployment.

## Розміщення

- Namespace/application: kryvda; Git: serpanchyk/kryvda, main, k8s/.
- HTTPS ingress: kryvda.thesis-i.com → frontend:8080 → api:8000.
  Nginx зберігає заборону запису через публічний /api/.
- PostgreSQL 16 на mac-master, PVC 20Gi; API/scraper на mac-node1,
  спільний PVC аватарок 2Gi; backup PVC 20Gi на mac-node2.
- Це не HA: local-path не переносить дані при втраті вузла. Не змінюйте
  nodeSelector для вже прив'язаного PVC без міграції даних.
- PVC мають Prune=false,Delete=false; namespace теж не слід видаляти:
  його видалення все одно видалить PVC, а reclaim policy local-path — Delete.
- API/scraper/worker/frontend працюють як UID 10001; PostgreSQL — UID 70.
  Frontend використовує окремий non-root nginx config, Compose не змінений.
- Базу створюють init SQL з database image. Sync hook міграцій застосовує
  versioned migrations після готовності PostgreSQL, до rollout застосунків.
  PVC і їх перші споживачі розміщені в однакових waves для WaitForFirstConsumer.
- Старі поди можуть працювати під час міграції: зміни схеми мають бути сумісні
  з попереднім релізом; для несумісних змін потрібне окреме maintenance window.

## Підготовка першого запуску

Ключі TELEGRAM_GATEWAY_URL, TELEGRAM_GATEWAY_TOKEN, LAPATHONIIA_API_KEY
надає власник інтеграцій. Без них application не реєструвати.

1. Перевірте контекст, не змінюючи його навмання:
   `kubectl config current-context`, `kubectl get nodes -o wide`.
2. Переконайтесь, що DNS kryvda.thesis-i.com веде на ingress кластера та
   Traefik віддає дійсний сертифікат для цього імені. Ingress використовує
   web та websecure за схемою інших сервісів кластера. На момент запуску
   Traefik повертає default self-signed certificate: для Cloudflare Full (strict)
   потрібно встановити origin certificate; для HTTP tunnel origin використовуйте web.
3. Скопіюйте `k8s/secret.example.yaml` у `k8s/secret.yaml`, встановіть права
   `chmod 600 k8s/secret.yaml`. Створіть POSTGRES_PASSWORD (`openssl rand -hex 24`)
   і LITELLM_MASTER_KEY (`openssl rand -hex 32`). Заповніть ключі інтеграцій.
   POSTGRES_DSN має формат
   `postgresql://telegram_monitor:<POSTGRES_PASSWORD>@postgres:5432/telegram_monitor`.
   Hex-пароль не потребує URL-escaping. Після ініціалізації БД зміна Secret
   сама по собі не змінює пароль ролі PostgreSQL.
4. Запустіть `sh scripts/deploy/seal-secrets.sh`. Скрипт шифрує Secret
   сертифікатом поточного кластера й додає sealed-secret.yaml у Kustomize.
   Закомітьте лише зашифрований файл та kustomization.yaml.
5. Створіть namespace: `kubectl apply -f k8s/namespace.yaml`.
   Для приватних GHCR packages створіть ghcr-secret у namespace kryvda
   з GitHub credential, який має read:packages. Не копіюйте чужі credentials.
6. Push у main запускає docker-build.yml: перевірки → п'ять amd64 образів →
   один commit тегів sha-<full SHA>. Workflow можна запустити вручну.
   GitHub Actions потребує packages:write та contents:write; branch protection
   має дозволяти CI-коміт або процес потрібно адаптувати до PR.
   Якщо джерела змінилися під час збірки, старий run не оновлює маніфести.
7. Після успішного CI отримайте commit з тегами (`git pull --ff-only`).
   Перевірте, що `rg ':bootstrap' k8s` нічого не знаходить.
   Початкові bootstrap-теги — навмисний запобіжник запуску до публікації образів.
8. `kubectl kustomize k8s` та
   `kubectl apply --dry-run=server -k k8s` перевіряють конфігурацію.
9. Зареєструйте застосунок: `kubectl apply -f k8s/argocd-app.yaml`.
   Bootstrap Application і secret.example.yaml не входять у resources Kustomize.
   Для приватного Git repo окремо налаштуйте repository credentials Argo CD.
10. Перевірте `kubectl get application kryvda -n argocd`,
    `kubectl get pods,pvc,jobs -n kryvda` та
    `curl --fail https://kryvda.thesis-i.com/api/health`.
    Перевірте також /api/channels/collection-health, /api/analysis/health,
    появу аватарок і завершення реального аналізу.

## Backup та відновлення

CronJob postgres-backup виконує одноразовий pg_dump щодня о 02:00 Europe/Kyiv,
зберігає 14 днів. Копії на іншому вузлі, але не поза кластером: налаштуйте
додаткове копіювання на зовнішній носій перед використанням як production.
Стежте за вільним місцем — local-path не підтримує expansion.

Ручний backup: `kubectl create job --from=cronjob/postgres-backup manual-backup-YYYYMMDD -n kryvda`.
Перевірте статус Job і цілісність dump через pg_restore --list, потім тестове
відновлення в окрему БД. Повний restore слід виконувати з вимкненою автоматичною
синхронізацією Argo CD і зупиненими api/scraper/worker, через pg_restore у PostgreSQL 16.
Після відновлення запустіть міграції та поверніть застосунки й auto-sync.
Rollback образів не відкочує схему БД.

## Обмеження перевірки

Без ключів інтеграцій неможливо підтвердити реальну колекцію Telegram та LLM-аналіз.
Docker builds і запуск контейнерів мають пройти в CI; dry-run Kubernetes
не перевіряє наявність образів, доступ до GHCR, DNS, сертифікат чи зовнішні API.

## Перевірка першого розгортання, 2026-10-16

GitHub Actions успішно зібрав усі п’ять образів; Argo CD Synced/Healthy.
Шість сервісів Running, міграції завершені, frontend → API health повертає 200.
Ручний запуск backup CronJob успішний. DNS налаштовано власником; публічні
https://kryvda.thesis-i.com/ і /api/health повертають 200 через Cloudflare
з успішною перевіркою TLS. Поточний TELEGRAM_GATEWAY_URL
посилається на відсутній локальний telegram-gateway; необхідна робоча адреса
або окреме розгортання gateway перед запуском збору.
