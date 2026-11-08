# Перенос с Turso в Supabase/PostgreSQL

Это подготовка подключения. Публикация кода сама по себе не переключает базу.
Старую Turso нельзя удалять до проверки переноса и резервной копии.

## Новая база

1. Supabase → New project, организация Free, имя ai-code-mentor.
2. Сохранить сгенерированный пароль базы в менеджере паролей.
3. Connect → Session pooler → PostgreSQL connection string (порт 5432).
   Использовать Session pooler для IPv4. Подставить пароль с URL-экранированием
   специальных символов. Не публиковать строку в Git, логах или чате.
4. Приложение работает в закрытой схеме `mentor`, а не `public`.
   Не добавлять `mentor` в Exposed schemas и не выдавать доступ anon/authenticated.
   Ключи anon/service_role приложению не нужны. TLS включён драйвером.

## Перенос актуальных данных без shell на бесплатном Render

В GitHub backend → Settings → Secrets and variables → Actions настроить:

- `TURSO_DATABASE_URL` — действующий адрес источника из Render;
- `TURSO_BACKUP_TOKEN` — действующий токен чтения источника;
- `BACKUP_ENCRYPTION_KEY` — ключ Fernet, сохранить отдельно от зашифрованной копии;
- `POSTGRES_MIGRATION_URL` — полная строка Session pooler новой базы.

Значения вводятся только в защищённые поля. Не изменять источник на старый локальный
снимок: в нём может не быть новых учеников и работ.

1. После развёртывания этого кода установить на Render `DATABASE_MAINTENANCE=true`.
   Дождаться завершения deploy. `/health` должен показывать этот флаг и Turso ok.
   Приложение временно отдаёт 503, новые запросы не меняют данные.
2. GitHub Actions → Verified Turso to PostgreSQL migration → Run workflow.
   Workflow проверяет режим обслуживания, сохраняет текущую зашифрованную копию,
   проверяет восстановление, импортирует все таблицы и сравнивает хеши каждой
   строки до commit и после переподключения. Существующие несовпадающие данные
   цели приводят к отказу; DROP TABLE и перезаписи нет.
3. Скачать encrypted-pre-migration artifact и сохранить ключ отдельно.
4. Только после успешного workflow добавить `DATABASE_URL` на Render из той же
   строки Session pooler. Пока оставить `DATABASE_MAINTENANCE=true`.
   `DATABASE_URL` имеет приоритет над переменными Turso.
5. Дождаться `/health`: healthy, database.backend=postgresql. Затем снять
   обслуживание (`DATABASE_MAINTENANCE=false`) и проверить вход существующего
   пользователя, старую группу, старую работу и новую отправку в тестовой группе.
6. Настроить секрет `DATABASE_URL` для workflow резервных копий и включить
   `BACKUPS_ENABLED=true` только после успешного ручного запуска backup.

До открытия записи в новую базу откат: убрать `DATABASE_URL`, сохранив Turso
переменные, дождаться healthy и снять обслуживание. После появления новых записей
в PostgreSQL нельзя просто переключаться назад — потребуется сверка/перенос этих
записей. Хранить обе базы до завершения проверки.

## Локальная проверка

Основные тесты остаются на SQLite. PostgreSQL проверяется отдельным набором на
настоящем изолированном сервере. `TEST_POSTGRES_URL` допускает только Unix socket
`/tmp/mentor-postgres-*`: тест очищает схему mentor в этой тестовой базе.

`python -m unittest discover -s tests -p test_postgres.py -q`

`PG_LOCAL_TEST=true` разрешает TLS-off только для указанного локального сокета;
на внешнем сервере TLS остаётся обязательным.
