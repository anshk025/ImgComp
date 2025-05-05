import os
import logging
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from io import BytesIO
from PIL import Image

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Compression levels
COMPRESSION_LEVELS = ["Low (85%)", "Medium (65%)", "High (45%)"]

def start(update, context):
    update.message.reply_text(
        "📷 Image Compressor Bot 📷\n\n"
        "Send me a JPG/PNG image to compress!\n"
        "Or use /compress to start."
    )

def help_command(update, context):
    update.message.reply_text(
        "How to use:\n"
        "1. Send me an image (JPG/PNG)\n"
        "2. Choose compression level\n"
        "3. Get your compressed file!\n\n"
        "Commands:\n"
        "/start - Welcome message\n"
        "/help - This message\n"
        "/compress - Start compression"
    )

def handle_image(update, context):
    # Check if we have a photo or document
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data['is_photo'] = True
    elif update.message.document:
        # Check if it's an image file
        mime_type = update.message.document.mime_type
        if not mime_type or not mime_type.startswith('image/'):
            update.message.reply_text("Please send an image file (JPG/PNG).")
            return ConversationHandler.END
        file_id = update.message.document.file_id
        context.user_data['is_photo'] = False
    else:
        update.message.reply_text("Please send an image file (JPG/PNG).")
        return ConversationHandler.END

    context.user_data['file_id'] = file_id
    
    # Show compression options
    markup = ReplyKeyboardMarkup(
        [COMPRESSION_LEVELS], one_time_keyboard=True, resize_keyboard=True
    )
    update.message.reply_text(
        "Choose compression level:",
        reply_markup=markup
    )
    
    return 1  # Next state

def compress_image(update, context):
    quality_map = {
        "Low (85%)": 85,
        "Medium (65%)": 65,
        "High (45%)": 45
    }
    
    level = update.message.text
    if level not in quality_map:
        update.message.reply_text("Invalid selection. Please try again.")
        return ConversationHandler.END

    update.message.reply_text("⏳ Compressing image...")

    try:
        file = context.bot.get_file(context.user_data['file_id'])
        img_bytes = BytesIO(file.download_as_bytearray())
        
        img = Image.open(img_bytes)
        output = BytesIO()
        
        # Determine format based on input or default to JPEG
        if context.user_data.get('is_photo', False) or img.format == 'PNG':
            img.save(output, format='PNG', optimize=True)
            ext = '.png'
        else:
            img.save(output, format='JPEG', quality=quality_map[level])
            ext = '.jpg'
        
        output.seek(0)
        update.message.reply_document(
            document=output,
            filename=f"compressed{ext}",
            caption=f"Here's your {level} compressed image!",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        update.message.reply_text("❌ Failed to compress image. Please try again.")
    
    return ConversationHandler.END

def cancel(update, context):
    update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    # Create the Updater and pass it your bot's token
    updater = Updater("7814507700:AAG5ATqlqX44MusXEpCUWzjcYxoOh6et0yM", use_context=True)
    
    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(Filters.photo | Filters.document.category("image"), handle_image),
            CommandHandler('compress', handle_image)
        ],
        states={
            1: [MessageHandler(Filters.text & ~Filters.command, compress_image)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_error_handler(error)
    
    # Start the Bot
    updater.start_polling()
    
    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()
