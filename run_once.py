"""One durable polling iteration for GitHub Actions; contains no credentials."""
import logging
import os
import time
import bot


def get(db, key, default='0'):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def put(db, key, value):
    value = str(value)
    if get(db, key, None) != value:
        with db:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, value))


def run(db, fetch=bot.fetch_posts, send=bot.send):
    try:
        posts = fetch()
        first = bot.ingest(db, posts)
        bot.deliver(db, send)
        if int(get(db, 'failures')) >= 3:
            send('✅ AP투자연구소 게시물 알림 확인이 복구되었습니다.')
        put(db, 'failures', 0)
        logging.info('check OK: posts=%d, first_baseline=%s', len(posts), first)
        return 0
    except Exception as exc:
        failures = int(get(db, 'failures')) + 1
        put(db, 'failures', failures)
        logging.error('check failed: %s (consecutive=%d)', type(exc).__name__, failures)
        if failures >= 3 and time.time() - float(get(db, 'last_warning')) >= 21600:
            try:
                send('⚠️ AP투자연구소 게시물 확인/알림이 연속 실패했습니다. GitHub Actions 실행 결과를 확인하세요.')
                put(db, 'last_warning', time.time())
            except Exception:
                logging.error('Telegram warning unavailable')
        return 1


def main():
    # Avoid silently initializing the baseline before the recipient is configured.
    for key in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'):
        if not os.environ.get(key, '').strip():
            logging.error('Missing required secret: %s', key)
            return 1
    db = bot.database(os.environ.get('STATE_DB', 'state/state.sqlite3'))
    try:
        return run(db)
    finally:
        db.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.error('Stopped: %s', type(exc).__name__)
        raise SystemExit(1)
