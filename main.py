import io
import logging
import os

import telebot
from PIL import Image

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_EDGE = 512

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("請先設定環境變數 TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)


def resize_to_png(data: bytes, keep_alpha: bool) -> bytes:
    """等比縮放到最大邊 512px 並輸出 PNG。keep_alpha=True 時保留透明通道。"""
    with Image.open(io.BytesIO(data)) as im:
        if keep_alpha:
            im = im.convert("RGBA") if im.mode != "RGBA" else im
        else:
            im = im.convert("RGB") if im.mode not in ("RGB", "RGBA") else im

        w, h = im.size
        scale = MAX_EDGE / max(w, h)
        new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        im = im.resize(new_size, Image.LANCZOS)

        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        return out.getvalue()


def send_png(chat_id: int, reply_to: int, png: bytes, filename: str, keep_alpha: bool) -> None:
    buf = io.BytesIO(png)
    buf.name = filename
    bot.send_document(
        chat_id,
        buf,
        visible_file_name=filename,
        reply_to_message_id=reply_to,
        caption=f"已縮到最大邊 {MAX_EDGE}px" + ("（保留透明）" if keep_alpha else ""),
    )


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    bot.reply_to(
        message,
        "Hi! 傳一張圖片給我，我會等比縮到最大邊 512px 並轉成 PNG。\n"
        "想保留透明背景請用『傳檔案 (send as file)』方式傳 PNG，"
        "不要用一般圖片訊息，否則會被 Telegram 在上傳時壓成 JPEG。",
    )


@bot.message_handler(content_types=["photo"])
def on_photo(message):
    """一般 photo 訊息已被 Telegram 壓成 JPEG，沒有透明通道。"""
    file_id = message.photo[-1].file_id
    try:
        info = bot.get_file(file_id)
        data = bot.download_file(info.file_path)
        png = resize_to_png(data, keep_alpha=False)
    except Exception:
        logger.exception("resize photo failed")
        bot.reply_to(message, "處理失敗 :(")
        return

    send_png(message.chat.id, message.message_id, png, "resized.png", keep_alpha=False)


@bot.message_handler(content_types=["document"])
def on_document(message):
    """以檔案方式傳來的圖片，PNG 要保留透明通道。"""
    doc = message.document
    mime = (doc.mime_type or "").lower()
    name = (doc.file_name or "").lower()

    image_exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff")
    if not (mime.startswith("image/") or name.endswith(image_exts)):
        bot.reply_to(message, "這不是圖片檔，跳過。")
        return

    keep_alpha = mime == "image/png" or name.endswith(".png")

    try:
        info = bot.get_file(doc.file_id)
        data = bot.download_file(info.file_path)
        png = resize_to_png(data, keep_alpha=keep_alpha)
    except Exception:
        logger.exception("resize document failed")
        bot.reply_to(message, "處理失敗 :(")
        return

    base = os.path.splitext(doc.file_name or "image")[0]
    send_png(message.chat.id, message.message_id, png, f"{base}_512.png", keep_alpha=keep_alpha)


if __name__ == "__main__":
    logger.info("Bot starting...")
    bot.infinity_polling(skip_pending=True)
