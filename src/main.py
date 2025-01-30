from src.bot import build_app
from src.tools.check_ip import check_ip
from src.config import settings


def main():
    check_ip()
    app = build_app(settings.bot_token)
    app.run_polling()


if __name__ == '__main__':
    main()
