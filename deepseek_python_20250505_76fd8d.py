import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from PIL import Image
from io import BytesIO
import tempfile
import subprocess
from pdf2image import convert_from_bytes
import img2pdf

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_ACTION, SELECTING_COMPRESSION = range(2)

# Supported file types
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf'}
COMPRESSION_LEVELS = ["Low", "Medium", "High", "Extreme"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}!\n\n"
        "I can help you with:\n"
        "1. Compressing PNG/JPG/JPEG/PDF files\n"
        "2. Converting PNG to PDF\n\n"
        "Just send me a file or use /compress or /convert commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message when the command /help is issued."""
    help_text = """
📁 <b>File Compression Bot</b> 📁

<b>Supported operations:</b>
- Compress PNG, JPG, JPEG, PDF files
- Convert PNG to PDF

<b>How to use:</b>
1. Send me a file (PNG/JPG/JPEG/PDF)
2. I'll ask what you want to do with it
3. For compression, select the desired level

<b>Commands:</b>
/start - Start the bot
/help - Show this help message
/compress - Start compression process
/convert - Start conversion process

<b>Compression levels:</b>
- Low: Minimal compression (best quality)
- Medium: Balanced quality/size
- High: Strong compression
- Extreme: Maximum compression (lowest quality)
"""
    await update.message.reply_text(help_text, parse_mode="HTML")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the user sending a document."""
    file = await context.bot.get_file(update.message.document)
    filename = update.message.document.file_name
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in SUPPORTED_EXTENSIONS:
        await update.message.reply_text(
            "❌ Unsupported file type. I only work with PNG, JPG, JPEG, and PDF files."
        )
        return ConversationHandler.END
    
    # Store file info in context
    context.user_data['file_id'] = file.file_id
    context.user_data['filename'] = filename
    context.user_data['extension'] = ext
    
    # Ask what to do with the file
    reply_keyboard = [["Compress", "Convert"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "What would you like to do with this file?",
        reply_markup=markup
    )
    
    return SELECTING_ACTION

async def select_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for compression level or proceed with conversion."""
    user_choice = update.message.text.lower()
    
    if user_choice == "compress":
        # Show compression level options
        markup = ReplyKeyboardMarkup(
            [COMPRESSION_LEVELS], one_time_keyboard=True, resize_keyboard=True
        )
        await update.message.reply_text(
            "Select compression level:",
            reply_markup=markup
        )
        return SELECTING_COMPRESSION
    elif user_choice == "convert":
        ext = context.user_data['extension']
        if ext != '.png':
            await update.message.reply_text(
                "❌ I can only convert PNG files to PDF.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🔄 Converting PNG to PDF...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Process the conversion
        await convert_png_to_pdf(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Invalid choice. Please select 'Compress' or 'Convert'.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

async def select_compression(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selected compression level and process the file."""
    compression_level = update.message.text.lower()
    context.user_data['compression_level'] = compression_level
    
    await update.message.reply_text(
        f"🔄 Compressing with {compression_level} level...",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Process the compression
    await compress_file(update, context)
    return ConversationHandler.END

async def compress_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Compress the file based on selected level."""
    file_id = context.user_data['file_id']
    filename = context.user_data['filename']
    ext = context.user_data['extension']
    compression_level = context.user_data['compression_level']
    
    # Get the file
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_input:
        temp_input.write(file_bytes)
        temp_input_path = temp_input.name
    
    try:
        if ext in ['.png', '.jpg', '.jpeg']:
            output_bytes = await compress_image(
                file_bytes, ext, compression_level
            )
            output_filename = f"compressed_{filename}"
        elif ext == '.pdf':
            output_bytes = await compress_pdf(
                file_bytes, compression_level
            )
            output_filename = f"compressed_{filename}"
        
        # Send the compressed file back
        await update.message.reply_document(
            document=output_bytes,
            filename=output_filename,
            caption=f"Here's your {compression_level} compressed file!"
        )
    except Exception as e:
        logger.error(f"Error during compression: {e}")
        await update.message.reply_text(
            "❌ An error occurred during compression. Please try again."
        )
    finally:
        if os.path.exists(temp_input_path):
            os.unlink(temp_input_path)

async def compress_image(image_bytes: bytes, ext: str, level: str) -> BytesIO:
    """Compress an image with the specified level."""
    quality_map = {
        'low': 85,
        'medium': 70,
        'high': 50,
        'extreme': 30
    }
    
    img = Image.open(BytesIO(image_bytes))
    
    # For PNG, we can optimize
    if ext == '.png':
        output = BytesIO()
        img.save(output, format='PNG', optimize=True, quality=quality_map[level])
    else:
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality_map[level])
    
    output.seek(0)
    return output

async def compress_pdf(pdf_bytes: bytes, level: str) -> BytesIO:
    """Compress a PDF using Ghostscript."""
    compression_map = {
        'low': ['-dPDFSETTINGS=/prepress'],
        'medium': ['-dPDFSETTINGS=/printer'],
        'high': ['-dPDFSETTINGS=/ebook'],
        'extreme': ['-dPDFSETTINGS=/screen']
    }
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_input:
        temp_input.write(pdf_bytes)
        temp_input_path = temp_input.name
    
    temp_output_path = temp_input_path.replace('.pdf', '_compressed.pdf')
    
    try:
        gs_command = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dNOPAUSE',
            '-dBATCH',
            '-dQUIET',
            '-dCompatibilityLevel=1.4',
            *compression_map[level],
            f'-sOutputFile={temp_output_path}',
            temp_input_path
        ]
        
        subprocess.run(gs_command, check=True)
        
        with open(temp_output_path, 'rb') as f:
            output_bytes = BytesIO(f.read())
        
        output_bytes.seek(0)
        return output_bytes
    finally:
        if os.path.exists(temp_input_path):
            os.unlink(temp_input_path)
        if os.path.exists(temp_output_path):
            os.unlink(temp_output_path)

async def convert_png_to_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert PNG to PDF."""
    file_id = context.user_data['file_id']
    filename = context.user_data['filename']
    
    # Get the file
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    
    try:
        img = Image.open(BytesIO(file_bytes))
        pdf_bytes = img2pdf.convert(img.filename)
        
        output_filename = os.path.splitext(filename)[0] + '.pdf'
        
        await update.message.reply_document(
            document=BytesIO(pdf_bytes),
            filename=output_filename,
            caption="Here's your converted PDF file!"
        )
    except Exception as e:
        logger.error(f"Error during conversion: {e}")
        await update.message.reply_text(
            "❌ An error occurred during conversion. Please try again."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text(
        "Operation cancelled.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("YOUR_TELEGRAM_BOT_TOKEN").build()
    
    # Add conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Document.ALL, handle_document),
            CommandHandler("compress", handle_document),
            CommandHandler("convert", handle_document)
        ],
        states={
            SELECTING_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_action)
            ],
            SELECTING_COMPRESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_compression)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()