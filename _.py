from flask import Flask, send_file, Response
from PIL import Image
import io # Used for the in-memory buffer

app = Flask(__name__)

@app.route('/get_image/<path:image_path>')
def get_image(image_path):
    # In a real app, you'd have proper path handling and security
    # For example: file_path = os.path.join(SECURE_UPLOAD_FOLDER, image_path)
    file_path = image_path 

    # Check the extension
    if file_path.lower().endswith('.tif') or file_path.lower().endswith('.tiff'):
        try:
            # 1. Open the TIFF image
            with Image.open(file_path) as img:
                # 2. Convert to a web-friendly mode like RGB
                # This handles palettes, CMYK, etc.
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 3. Save to an in-memory buffer
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85) # You can adjust quality
                buffer.seek(0)
                
                # 4. Send the buffer's content with the JPEG mimetype
                return send_file(
                    buffer,
                    mimetype='image/jpeg',
                    as_attachment=False # Important to display it, not download it
                )
        except Exception as e:
            # Handle errors like file not found or corrupted image
            print(f"Error converting TIFF: {e}")
            return "Error processing image", 500

    # For JPG and other supported formats, you can send them directly
    elif file_path.lower().endswith('.jpg') or file_path.lower().endswith('.jpeg'):
        return send_file(image_path, mimetype='image/jpeg')
        
    # Add other file types as needed (PNG, etc.)
    else:
        return "Unsupported file type", 400

# To run this example:
# 1. Save the code as app.py
# 2. Place a .tif file (e.g., my_image.tif) in the same directory.
# 3. Run `flask run`
# 4. Access http://127.0.0.1:5000/get_image/my_image.tif in your browser.