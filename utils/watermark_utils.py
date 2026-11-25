from io import BytesIO
import base64
import os
from PIL import ImageDraw, ImageFont, Image, ImageEnhance
from database_functions.watermark_db import get_watermark, get_any_watermark_for_channel


def apply_watermark_to_image(image_data: bytes, watermark_data: str, position: str = 'bottom-right', 
                           size_percent: int = 50, opacity: int = 100):
    try:
        if not image_data or len(image_data) < 100:
            print(f"❌ Недійсні дані зображення: {len(image_data) if image_data else 0} байт")
            return None
        
        watermark_bytes = base64.b64decode(watermark_data)
        
        try:
            main_image = Image.open(BytesIO(image_data)).convert("RGBA")
        except Exception as img_error:
            print(f"❌ Не можу відкрити основне зображення: {img_error}")
            return None
        
        try:
            watermark = Image.open(BytesIO(watermark_bytes)).convert("RGBA")
        except Exception as wm_error:
            print(f"❌ Не можу відкрити водяний знак: {wm_error}")
            return None
        
        main_width, main_height = main_image.size
        watermark_width = int(main_width * size_percent / 100)
        watermark_height = int(watermark.height * watermark_width / watermark.width)
        
        watermark = watermark.resize((watermark_width, watermark_height), Image.Resampling.LANCZOS)
        
        if opacity < 100:
            alpha = watermark.split()[-1]
            alpha = ImageEnhance.Brightness(alpha).enhance(opacity / 100.0)
            watermark.putalpha(alpha)
        
        positions = {
            'top-left': (10, 10),
            'top-center': ((main_width - watermark_width) // 2, 10),
            'top-right': (main_width - watermark_width - 10, 10),
            'center-left': (10, (main_height - watermark_height) // 2),
            'center': ((main_width - watermark_width) // 2, (main_height - watermark_height) // 2),
            'center-right': (main_width - watermark_width - 10, (main_height - watermark_height) // 2),
            'bottom-left': (10, main_height - watermark_height - 10),
            'bottom-center': ((main_width - watermark_width) // 2, main_height - watermark_height - 10),
            'bottom-right': (main_width - watermark_width - 10, main_height - watermark_height - 10)
        }
        
        x, y = positions.get(position, positions['bottom-right'])
        
        main_image.paste(watermark, (x, y), watermark)
        
        output = BytesIO()
        main_image.convert("RGB").save(output, format="JPEG", quality=95)
        return output.getvalue()
        
    except Exception as e:
        print(f"❌ Помилка накладання водяного знаку: {e}")
        return None


def image_to_base64(image_data: bytes):
    try:
        return base64.b64encode(image_data).decode('utf-8')
    except Exception as e:
        print(f"❌ Помилка конвертації у base64: {e}")
        return None




def create_preview_image(watermark_data: str, position: str = 'bottom-right', 
                        size_percent: int = 50, opacity: int = 100):
    try:
        test_image = Image.new("RGBA", (400, 300), (240, 240, 240, 255))

        draw = ImageDraw.Draw(test_image)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)
        except:
            font = ImageFont.load_default()

        text = "Превʼю водяного знаку"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        text_x = (400 - text_width) // 2
        text_y = (300 - text_height) // 2
        draw.text((text_x, text_y), text, fill=(100, 100, 100, 255), font=font)

        output = BytesIO()
        test_image.convert("RGB").save(output, format="JPEG", quality=95)
        test_image_data = output.getvalue()

        result = apply_watermark_to_image(test_image_data, watermark_data, position, size_percent, opacity)
        return result
        
    except Exception as e:
        print(f"❌ Помилка створення превʼю: {e}")
        return None




async def apply_watermark_to_telegram_photo(bot, chat_id: int, user_id: int, channel_id: int, file_id: str):
    """
    Завантажує фото з Telegram, накладає водяний знак (manual або будь-який для каналу),
    відправляє у chat_id і повертає новий file_id. Тимчасове повідомлення видаляється.
    """
    from aiogram.types import FSInputFile
    import tempfile

    cid = str(channel_id)
    wm = get_watermark(user_id, cid, "manual")
    if not wm:
        wm = get_any_watermark_for_channel(user_id, cid)
    if not wm:
        return None
    try:
        f = await bot.get_file(file_id)
        buf = await bot.download_file(f.file_path)
        raw = buf.read() if hasattr(buf, "read") else buf.getvalue()
        if not raw or len(raw) < 100:
            return None
        out = apply_watermark_to_image(
            raw,
            wm["watermark_data"],
            wm["position"],
            wm["size_percent"],
            wm["opacity"],
        )
        if not out:
            return None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(out)
            tmp_path = tmp.name
        try:
            sent = await bot.send_photo(chat_id=chat_id, photo=FSInputFile(tmp_path))
            new_id = sent.photo[-1].file_id
            await bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
            return new_id
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    except Exception as e:
        print(f"❌ apply_watermark_to_telegram_photo: {e}")
        return None
