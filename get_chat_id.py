"""Run locally with a new dedicated bot, never inside public Actions logs."""
import getpass
import os
import bot

print('새 전용 봇의 chat ID 확인 도구입니다. 기존 서비스에서 쓰는 봇에는 사용하지 마세요.')
print('텔레그램에서 본인 봇에 /start 를 먼저 보내세요.')
os.environ['TELEGRAM_BOT_TOKEN'] = getpass.getpass('BotFather 토큰 (입력 내용 숨김): ').strip()
try:
    if bot.telegram('getWebhookInfo', {}).get('url'):
        print('이미 연결된 webhook이 있어 중단합니다. 기존 설정의 chat ID를 사용하세요.')
    else:
        updates = bot.telegram('getUpdates', {'timeout': 0})
        chats = {u['message']['chat']['id'] for u in updates
                 if u.get('message', {}).get('chat', {}).get('type') == 'private'}
        if len(chats) == 1:
            print('개인 대화방 CHAT ID:', next(iter(chats)))
            print('본인이 /start 를 보낸 새 봇인지 확인한 뒤 GitHub Secret에 입력하세요.')
        elif not chats:
            print('대화가 없습니다. 봇에게 /start 를 보낸 다음 다시 실행하세요.')
        else:
            print('여러 개인 대화방이 있습니다. 자동 선택하지 않습니다. 본인 채팅 ID를 확인하세요.')
except Exception as exc:
    print('조회 실패:', type(exc).__name__, '토큰과 인터넷 연결을 확인하세요.')
finally:
    os.environ.pop('TELEGRAM_BOT_TOKEN', None)
