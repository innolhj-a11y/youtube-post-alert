"""Public YouTube posts -> Telegram. Python 3.12+, standard library only."""
import argparse
import json
import logging
import os
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

URL = 'https://www.youtube.com/@ap5798/posts'
CHANNEL_ID = 'UCUFUOdQwKTWda7kKqxQwMxw'

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

def parse_posts(html):
    match = re.search(r'(?:var\s+ytInitialData|window\["ytInitialData"\])\s*=\s*', html)
    if not match:
        raise ValueError('YouTube initial data missing')
    data = json.JSONDecoder().raw_decode(html[match.end():])[0]
    metadata = data.get('metadata', {}).get('channelMetadataRenderer', {})
    if metadata.get('externalId') != CHANNEL_ID:
        raise ValueError('Unexpected channel or unavailable page')
    posts = {}
    for node in walk(data.get('contents', {})):
        post = node.get('backstagePostRenderer')
        if not post:
            continue
        pid = post.get('postId', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', pid):
            raise ValueError('Invalid post ID')
        content = post.get('contentText', {})
        body = content.get('simpleText') or ''.join(r.get('text', '') for r in content.get('runs', []))
        posts[pid] = body or '(이미지·설문 등: 원문 링크를 확인하세요.)'
    if not posts:
        raise ValueError('No readable posts; refusing to change baseline')
    return posts

def fetch_posts():
    req = urllib.request.Request(URL, headers={
        'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=45) as response:
        return parse_posts(response.read().decode('utf-8'))

def telegram(method, payload):
    token = os.environ['TELEGRAM_BOT_TOKEN'].strip()
    req = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method,
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    # Never log the request URL: it contains a secret.
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected request')
    return result['result']

def send(text):
    return telegram('sendMessage', {'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': text})

def database(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, body TEXT, sent INTEGER NOT NULL)')
    return db

def ingest(db, posts):
    first = not db.execute("SELECT 1 FROM meta WHERE key='initialized'").fetchone()
    with db:
        for pid, body in reversed(list(posts.items())):
            db.execute('INSERT OR IGNORE INTO posts VALUES (?, ?, ?)', (pid, body, int(first)))
        if first:
            db.execute("INSERT INTO meta VALUES ('initialized', '1')")
    return first

def deliver(db, sender=send):
    for pid, body in db.execute('SELECT id, body FROM posts WHERE sent=0 ORDER BY rowid').fetchall():
        # Cap UTF-16 units too: slicing to 1700 codepoints is safe even for emoji.
        excerpt = body[:1700] + ('…' if len(body) > 1700 else '')
        sender('🔔 AP투자연구소 새 게시물\n\n' + excerpt + '\n\nhttps://www.youtube.com/post/' + pid)
        with db:
            db.execute('UPDATE posts SET sent=1 WHERE id=?', (pid,))
        time.sleep(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Read YouTube only; no state or messages')
    parser.add_argument('--test-message', action='store_true')
    parser.add_argument('--chat-id', action='store_true', help='For a NEW unused bot only; inspect /start chats')
    args = parser.parse_args()
    if args.check:
        posts = fetch_posts()
        print(f'YouTube 확인 성공: {len(posts)}개 게시물, 채널 ID 일치')
        return
    if args.chat_id:
        if telegram('getWebhookInfo', {}).get('url'):
            raise RuntimeError('Webhook already configured. Do not use this helper on an existing bot.')
        updates = telegram('getUpdates', {'timeout': 0})
        chats = {u['message']['chat']['id']: u['message']['chat'].get('type') for u in updates if 'message' in u}
        print(chats or '봇에게 /start 를 보낸 다음 다시 실행하세요.')
        return
    if args.test_message:
        send('✅ AP투자연구소 게시물 알림 봇: 텔레그램 연결 테스트 성공')
        return
    if not os.environ.get('TELEGRAM_BOT_TOKEN') or not os.environ.get('TELEGRAM_CHAT_ID'):
        raise ValueError('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID')
    db = database(os.environ.get('STATE_DB', '/data/state.sqlite3'))
    interval = max(60, int(os.environ.get('POLL_SECONDS', '300')))
    failures = 0
    last_warning = 0
    while True:
        try:
            posts = fetch_posts()
            first = ingest(db, posts)
            deliver(db)
            logging.info('check OK: %s posts; baseline=%s', len(posts), first)
            if failures >= 3:
                send('✅ 유튜브 게시물 확인이 복구되었습니다.')
            failures = 0
        except Exception as exc:
            failures += 1
            logging.error('check failed (%s); count=%s', type(exc).__name__, failures)
            if failures >= 3 and time.time() - last_warning > 21600:
                try:
                    send('⚠️ 유튜브 게시물 확인 또는 알림 전송이 연속 실패했습니다. 서버 로그를 확인하세요.')
                    last_warning = time.time()
                except Exception:
                    logging.error('Telegram warning unavailable')
        time.sleep(interval)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        main()
    except Exception as exc:
        # Sanitized diagnostic; never print token-bearing HTTP errors.
        logging.error('Stopped: %s. Check settings and connectivity.', type(exc).__name__)
        raise SystemExit(1)
