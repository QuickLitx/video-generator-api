import os
import logging
from flask import Flask, request, jsonify
from video_generator_migration import VideoGenerator
from models_migration import db, VideoGeneration
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)

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
    # Fallback for development
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///video_generator.db"
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()

# Initialize services
video_generator = VideoGenerator()

@app.route('/startup', methods=['POST'])
def startup_trigger():
    """Endpoint to wake up and initialize the application from Make"""
    try:
        # Verify database connection
        db.session.execute(db.text('SELECT 1'))
        db.session.commit()
        
        # Ensure directories exist
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
    Expects JSON with image_url and audio_url fields
    """
    video_record = None
    try:
        # Validate request content type
        if not request.is_json:
            return jsonify({
                "error": "Content-Type must be application/json"
            }), 400
        
        data = request.get_json()
        
        # Validate required parameters
        if not data:
            return jsonify({
                "error": "No JSON data provided"
            }), 400
            
        image_url = data.get('image_url')
        audio_url = data.get('audio_url')
        
        # Video configuration parameters (optional)
        video_config = {
            'width': data.get('width', 1080),
            'height': data.get('height', 1920),
            'bitrate': data.get('bitrate', '128k'),
            'frame_rate': data.get('frame_rate', 24),
            'crf': data.get('crf', 28),
            'music_volume': data.get('music_volume', 0.06)
        }
        
        # Optional background music URL
        background_music_url = data.get('background_music_url')
        
        if not image_url or not audio_url:
            return jsonify({
                "error": "Both image_url and audio_url are required"
            }), 400
        
        app.logger.info(f"Processing video generation request: image={image_url}, audio={audio_url}")
        
        # Generate video
        try:
            video_data = video_generator.create_vertical_video(image_url, audio_url, background_music_url, video_config)
        except Exception as e:
            app.logger.error(f"Video generation failed: {str(e)}")
            return jsonify({
                "error": f"Video generation failed: {str(e)}"
            }), 500
        
        if not video_data:
            return jsonify({
                "error": "Failed to generate video"
            }), 500
        
        # Save video to static files directory for direct access
        static_folder = app.static_folder or 'static'
        static_dir = os.path.join(static_folder, 'videos')
        os.makedirs(static_dir, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{timestamp}.mp4"
        video_path = os.path.join(static_dir, filename)
        
        # Save video file
        with open(video_path, 'wb') as f:
            f.write(video_data)
        
        # Generate public URL for the video
        video_url = request.url_root + f"static/videos/{filename}"
        
        app.logger.info(f"Video successfully generated and saved: {video_url}")
        
        return jsonify({
            "video_url": video_url,
            "file_size": len(video_data),
            "timestamp": timestamp
        })
        
    except Exception as e:
        app.logger.error(f"Error generating video: {str(e)}")
        return jsonify({
            "error": f"Internal server error: {str(e)}"
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal server error"
    }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
