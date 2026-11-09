# Бекап бази WordSnap

Головна база живе в Supabase (проєкт `zewsrfqcephiyfevnzxg`, PostgreSQL 17).
На тарифі Free Supabase бекапів не робить, тому їх робить GitHub Actions:
workflow `.github/workflows/db-backup.yml` щодня о 03:17 UTC знімає `pg_dump`
схеми `public` і кладе його артефактом на 90 днів.

Репозиторій публічний, тож дамп завжди зашифрований (gpg, AES256, симетричний
ключ). Без ключа артефакт марний.

## Секрети

| Де | Що |
|---|---|
| GitHub secret `WORDSNAP_BACKUP_DB_URL` | URL бази через session pooler, порт 5432, без `+asyncpg` |
| GitHub secret `WORDSNAP_BACKUP_PASSPHRASE` | ключ шифрування |
| `.env` (dotenvx) `BACKUP_PASSPHRASE` | копія того самого ключа, щоб не загубити |

Txn pooler на порту 6543 для `pg_dump` не годиться, потрібен session-режим 5432.

## Зняти дамп вручну

Actions → db-backup → Run workflow. Або локально (потрібен `pg_dump` 17+,
`brew install libpq`):

```sh
cd ~/projects/wordsnap
dotenvx run -- sh -c 'pg_dump "$(printf %s "$DATABASE_URL" | sed -E "s#postgresql\+asyncpg://#postgresql://#; s#:6543/#:5432/#")" --schema=public --no-owner --no-privileges -Fc -f wordsnap-local.dump'
```

## Відновити

1. Завантажити артефакт з потрібного запуску Actions, розпакувати zip.
2. Розшифрувати:

```sh
dotenvx run -- sh -c 'gpg --batch --decrypt --passphrase "$BACKUP_PASSPHRASE" --pinentry-mode loopback -o wordsnap.dump wordsnap-YYYYMMDD-HHMM.dump.gpg'
```

3. Залити в порожню базу (або в новий проєкт Supabase):

```sh
pg_restore --no-owner --no-privileges --clean --if-exists -d "$TARGET_DB_URL" wordsnap.dump
```

Після відновлення запустити бекенд: `core/auto_migrate.py` на старті дотягне
схему, якщо дамп старіший за код.
