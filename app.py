import os
import logging
from flask import Flask, request, jsonify
from video_generator import VideoGenerator
from models import db, VideoGeneration
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default-secret-key")

# Configure database
database_url = os.environ.get("DATABASE_URL")
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///video_generator.db"
db.init_app(app)

with app.app_context():
    db.create_all()

video_generator = VideoGenerator()


@app.route('/', methods=['GET'])
def index():
    """Root endpoint - API status"""
    return jsonify({
        "status": "online",
        "service": "Video Generator API",
        "version": "1.0",
        "endpoints": {
            "startup": "/startup (POST)",
            "generate_video": "/generate-video (POST)",
            "health": "/health (GET)"
        },
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        db.session.execute(db.text('SELECT 1'))
        db.session.commit()

        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500


@app.route('/startup', methods=['POST'])
def startup_trigger():
    """Endpoint to wake up and initialize the application from Make"""
    try:
        db.session.execute(db.text('SELECT 1'))
        db.session.commit()

        static_folder = app.static_folder or 'static'
        static_dir = os.path.join(static_folder, 'videos')
        os.makedirs(static_dir, exist_ok=True)

        app.logger.info("Application startup triggered from Make automation")

        return jsonify({
            "status": "started",
            "message": "Application is now ready for requests",
            "timestamp": datetime.utcnow().isoformat(),
            "ready_for_video_generation": True
        }), 200

    except Exception as e:
        app.logger.error(f"Startup trigger failed: {str(e)}")
        return jsonify({
            "status": "failed",
            "message": f"Failed to start application: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
            "ready_for_video_generation": False
        }), 500


@app.route('/generate-video', methods=['POST'])
def generate_video():
    """
    Main endpoint to generate vertical videos from image and audio URLs
    Optimized for Render timeout - same workflow as before
    """
    try:
        if not request.is_json:
            return jsonify({"error":
                            "Content-Type must be application/json"}), 400

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        image_url = data.get('image_url')
        audio_url = data.get('audio_url')

        if not image_url or not audio_url:
            return jsonify(
                {"error": "Both image_url and audio_url are required"}), 400

        app.logger.info(
            f"Processing video generation request: image={image_url}, audio={audio_url}"
        )

        # Optimized video configuration for faster processing
        video_config = {
            'width': 1080,  # Keep original resolution
            'height': 1920,  # Keep original resolution
            'bitrate': '512k',  # Reduced for speed
            'frame_rate': 20,  # Reduced from 24fps
            'crf': 30,  # Higher compression for speed
            'music_volume': data.get('music_volume', 0.06),
            'preset': 'ultrafast',  # FFmpeg preset for speed
            'tune': 'fastdecode'  # Optimize for fast processing
        }

        background_music_url = data.get('background_music_url')

        # Generate video with optimized settings
        video_data = video_generator.create_vertical_video(
            image_url, audio_url, background_music_url, video_config)

        if not video_data:
            return jsonify({"error": "Failed to generate video"}), 500

        # Save video file
        static_folder = 'static'
        static_dir = os.path.join(static_folder, 'videos')
        os.makedirs(static_dir, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{timestamp}.mp4"
        video_path = os.path.join(static_dir, filename)

        with open(video_path, 'wb') as f:
            f.write(video_data)

        # Get domain from request
        domain = request.headers.get('Host', 'localhost:5000')
        protocol = 'https' if request.headers.get(
            'X-Forwarded-Proto') == 'https' else 'http'
        video_url = f"{protocol}://{domain}/static/videos/{filename}"

        app.logger.info(f"Video generated successfully: {video_url}")

        # Same response format as before
        return jsonify({
            "status": "success",
            "video_url": video_url,
            "file_size": len(video_data),
            "timestamp": timestamp,
            "message": "Video generated successfully"
        }), 200

    except Exception as e:
        app.logger.error(f"Error generating video: {str(e)}")
        return jsonify({"error": f"Failed to generate video: {str(e)}"}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": {
            "root": "/ (GET)",
            "health": "/health (GET)",
            "startup": "/startup (POST)",
            "generate_video": "/generate-video (POST)"
        }
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)),
            debug=False)
