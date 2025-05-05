import os
import logging
from typing import Optional
from io import BytesIO

from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from PIL import Image
import pdf2image
from pdf2image import convert_from_bytes
from fpdf import FPDF
import fitz  # PyMuPDF

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define states for conversation
SELECT_COMPRESSION, SELECT_CONVERSION = range(2)

# Bot token from BotFather
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# Supported file types
SUPPORTED_TYPES = [".png", ".jpg", ".jpeg", ".pdf"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}!\n\n"
        "I can help you with:\n"
        "1. Compressing PNG/JPG/JPEG/PDF files\n"
        "2. Converting PNG to PDF\n\n"
        "Just send me a file and I'll guide you through the options!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "📁 Supported file types: PNG, JPG, JPEG, PDF\n\n"
        "🔧 Available functions:\n"
        "- Compress files (reduce file size)\n"
        "- Convert PNG to PDF\n\n"
        "Just send me a file to get started!"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the uploaded document and ask for action."""
    document = update.message.document
    
    # Check file extension
    file_ext = os.path.splitext(document.file_name.lower())[1]
    if file_ext not in SUPPORTED_TYPES:
        await update.message.reply_text(
            "❌ Unsupported file type. I only work with PNG, JPG, JPEG, and PDF files."
        )
        return ConversationHandler.END
    
    # Save file info in context
    context.user_data["file_id"] = document.file_id
    context.user_data["file_name"] = document.file_name
    context.user_data["file_ext"] = file_ext
    
    # Ask user what they want to do
    keyboard = [["Compress", "Convert"]]
    if file_ext != ".png":
        keyboard = [["Compress"]]  # Only offer compress for non-PNG files
    
    await update.message.reply_text(
        f"Received {document.file_name}. What would you like to do?",
        reply_markup={"keyboard": keyboard, "one_time_keyboard": True},
    )
    
    return SELECT_CONVERSION if file_ext == ".png" else SELECT_COMPRESSION

async def select_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle conversion selection."""
    choice = update.message.text.lower()
    
    if choice == "convert":
        # Proceed with PNG to PDF conversion
        return await convert_png_to_pdf(update, context)
    elif choice == "compress":
        # Ask for compression level
        await update.message.reply_text(
            "Please enter the compression quality (1-100, where 100 is best quality):"
        )
        return SELECT_COMPRESSION
    else:
        await update.message.reply_text("Invalid choice. Please select 'Compress' or 'Convert'.")
        return SELECT_CONVERSION

async def select_compression(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle compression level selection."""
    try:
        quality = int(update.message.text)
        if not 1 <= quality <= 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a number between 1 and 100.")
        return SELECT_COMPRESSION
    
    context.user_data["quality"] = quality
    return await compress_file(update, context)

async def convert_png_to_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Convert PNG to PDF."""
    file_id = context.user_data["file_id"]
    file_name = context.user_data["file_name"]
    
    # Download the file
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Create PDF from PNG
    pdf = FPDF()
    pdf.add_page()
    
    # Save PNG to temporary file
    temp_png = "temp.png"
    with open(temp_png, "wb") as f:
        f.write(file_bytes)
    
    # Add image to PDF (scaled to A4 page)
    pdf.image(temp_png, x=10, y=10, w=190)
    
    # Save PDF to bytes
    output_pdf = "converted.pdf"
    pdf.output(output_pdf)
    
    # Send the PDF back to user
    with open(output_pdf, "rb") as f:
        await update.message.reply_document(
            document=InputFile(f, filename=f"converted_{file_name.replace('.png', '.pdf')}"),
            caption="Here's your converted PDF file!"
        )
    
    # Clean up
    os.remove(temp_png)
    os.remove(output_pdf)
    
    return ConversationHandler.END

async def compress_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Compress the uploaded file."""
    file_id = context.user_data["file_id"]
    file_name = context.user_data["file_name"]
    file_ext = context.user_data["file_ext"]
    quality = context.user_data.get("quality", 85)  # Default quality if not specified
    
    # Download the file
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    
    try:
        if file_ext in [".png", ".jpg", ".jpeg"]:
            # Compress image
            with Image.open(BytesIO(file_bytes)) as img:
                # Convert to RGB if CMYK to avoid errors
                if img.mode == 'CMYK':
                    img = img.convert('RGB')
                
                # Save compressed image to bytes
                output_buffer = BytesIO()
                img.save(output_buffer, format=img.format, quality=quality, optimize=True)
                output_buffer.seek(0)
                
                # Send compressed file back
                await update.message.reply_document(
                    document=InputFile(output_buffer, filename=f"compressed_{file_name}"),
                    caption=f"Here's your compressed image (quality: {quality})!"
                )
                
        elif file_ext == ".pdf":
            # Compress PDF
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            
            # Set compression options
            for page in doc:
                page.set_compression(True)
            
            # Save compressed PDF to bytes
            output_buffer = BytesIO()
            doc.save(output_buffer, deflate=True, garbage=4)
            output_buffer.seek(0)
            
            # Send compressed PDF back
            await update.message.reply_document(
                document=InputFile(output_buffer, filename=f"compressed_{file_name}"),
                caption=f"Here's your compressed PDF!"
            )
            
    except Exception as e:
        logger.error(f"Error compressing file: {e}")
        await update.message.reply_text("❌ An error occurred while processing your file.")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # Add conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, handle_document)],
        states={
            SELECT_CONVERSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_conversion)
            ],
            SELECT_COMPRESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_compression)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()