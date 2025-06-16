import os
import logging
from flask import Flask, request, jsonify
from video_generator import VideoGenerator
from models import db, VideoGeneration
from datetime import datetime
import threading
import time

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

# Store for async video generation results
video_results = {}

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

def generate_video_async(image_url, audio_url, background_music_url, video_config, job_id):
    """Generate video in background thread"""
    try:
        app.logger.info(f"Starting async video generation for job {job_id}")
        
        video_data = video_generator.create_vertical_video(image_url, audio_url, background_music_url, video_config)
        
        if not video_data:
            video_results[job_id] = {
                "status": "failed",
                "error": "Failed to generate video"
            }
            return
        
        # Save video file
        static_folder = 'static'
        static_dir = os.path.join(static_folder, 'videos')
        os.makedirs(static_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{job_id}_{timestamp}.mp4"
        video_path = os.path.join(static_dir, filename)
        
        with open(video_path, 'wb') as f:
            f.write(video_data)
        
        # Store result
        video_results[job_id] = {
            "status": "completed",
            "video_url": f"/static/videos/{filename}",
            "file_size": len(video_data),
            "timestamp": timestamp
        }
        
        app.logger.info(f"Video generation completed for job {job_id}")
        
    except Exception as e:
        app.logger.error(f"Video generation failed for job {job_id}: {str(e)}")
        video_results[job_id] = {
            "status": "failed",
            "error": str(e)
        }

@app.route('/generate-video', methods=['POST'])
def generate_video():
    """
    Start video generation and return immediately with job ID
    For Render timeout compatibility
    """
    try:
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        image_url = data.get('image_url')
        audio_url = data.get('audio_url')
        
        if not image_url or not audio_url:
            return jsonify({"error": "Both image_url and audio_url are required"}), 400
        
        # Video configuration
        video_config = {
            'width': data.get('width', 720),  # Reduced for faster processing
            'height': data.get('height', 1280),
            'bitrate': data.get('bitrate', '64k'),  # Lower bitrate
            'frame_rate': data.get('frame_rate', 15),  # Lower framerate
            'crf': data.get('crf', 32),  # Higher compression
            'music_volume': data.get('music_volume', 0.06)
        }
        
        background_music_url = data.get('background_music_url')
        
        # Generate unique job ID
        job_id = f"{int(time.time())}_{hash(image_url + audio_url) % 10000}"
        
        app.logger.info(f"Starting video generation job {job_id}: image={image_url}, audio={audio_url}")
        
        # Store initial status
        video_results[job_id] = {
            "status": "processing",
            "message": "Video generation in progress"
        }
        
        # Start async generation
        thread = threading.Thread(
            target=generate_video_async,
            args=(image_url, audio_url, background_music_url, video_config, job_id),
            daemon=True
        )
        thread.start()
        
        # Return immediately for Render compatibility
        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "message": "Video generation started",
            "check_status_url": f"/status/{job_id}",
            "estimated_time": "60-120 seconds"
        }), 202
        
    except Exception as e:
        app.logger.error(f"Error starting video generation: {str(e)}")
        return jsonify({"error": f"Failed to start video generation: {str(e)}"}), 500

@app.route('/status/<job_id>', methods=['GET'])
def check_status(job_id):
    """Check video generation status"""
    if job_id not in video_results:
        return jsonify({"error": "Job not found"}), 404
    
    result = video_results[job_id]
    
    # Clean up completed/failed jobs after returning result
    if result["status"] in ["completed", "failed"]:
        # Keep result for a bit longer in case of retries
        pass
    
    return jsonify(result)

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": {
            "root": "/ (GET)",
            "health": "/health (GET)", 
            "startup": "/startup (POST)",
            "generate_video": "/generate-video (POST)",
            "status": "/status/<job_id> (GET)"
        }
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
