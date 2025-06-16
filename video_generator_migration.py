import os
import tempfile
import subprocess
import requests
import logging
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

class VideoGenerator:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
    
    def download_file(self, url, file_type="unknown"):
        """Download file from URL and return bytes data"""
        try:
            logger.info(f"Downloading {file_type} from: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            if content_type and content_type != 'application/binary':
                logger.warning(f"Unexpected content type for {file_type}: {content_type}")
            
            return response.content
        except Exception as e:
            logger.error(f"Failed to download {file_type} from {url}: {str(e)}")
            raise Exception(f"Download failed: {str(e)}")
    
    def process_image_for_vertical_video(self, image_data, target_width=1080, target_height=1920, effect_type="none"):
        """Process image to fit specified vertical format with visual effects"""
        try:
            # Open image
            image = Image.open(BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            original_width, original_height = image.size
            target_ratio = target_width / target_height
            original_ratio = original_width / original_height
            
            if original_ratio > target_ratio:
                # Image is wider than target ratio - crop width
                new_height = original_height
                new_width = int(new_height * target_ratio)
                left = (original_width - new_width) // 2
                image = image.crop((left, 0, left + new_width, new_height))
            else:
                # Image is taller than target ratio - crop height
                new_width = original_width
                new_height = int(new_width / target_ratio)
                top = (original_height - new_height) // 2
                image = image.crop((0, top, new_width, top + new_height))
            
            # Resize to target dimensions
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Save processed image
            processed_image_io = BytesIO()
            image.save(processed_image_io, format='JPEG', quality=90)
            processed_image_io.seek(0)
            
            return processed_image_io.getvalue()
            
        except Exception as e:
            logger.error(f"Image processing failed: {str(e)}")
            raise Exception(f"Image processing error: {str(e)}")
    
    def create_vertical_video(self, image_url, audio_url, background_music_url=None, config=None):
        """Create vertical video from image and audio URLs with optional background music"""
        try:
            logger.info("Starting video generation process")
            
            # Default configuration
            if config is None:
                config = {}
            
            width = config.get('width', 1080)
            height = config.get('height', 1920)
            bitrate = config.get('bitrate', '128k')
            frame_rate = config.get('frame_rate', 24)
            crf = config.get('crf', 28)
            music_volume = config.get('music_volume', 0.06)
            
            # Download and process image
            image_data = self.download_file(image_url, "image")
            processed_image_data = self.process_image_for_vertical_video(image_data, width, height)
            
            # Download audio
            audio_data = self.download_file(audio_url, "audio")
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as img_file:
                img_file.write(processed_image_data)
                image_path = img_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as audio_file:
                audio_file.write(audio_data)
                audio_path = audio_file.name
            
            # Get audio duration for timeout calculation
            duration_cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
            ]
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
            
            try:
                audio_duration = float(duration_result.stdout.strip())
                logger.info(f"Audio duration: {audio_duration} seconds")
            except:
                audio_duration = 60.0  # Default fallback
                logger.warning("Could not determine audio duration, using 60s default")
            
            # Calculate timeout (base 300s + 20s per minute of audio)
            timeout_seconds = int(300 + (audio_duration / 60) * 20)
            logger.info(f"Using timeout of {timeout_seconds} seconds for {audio_duration}s audio")
            
            # Create output file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                output_path = output_file.name
            
            # Initialize variables
            music_path = None
            
            try:
                if background_music_url:
                    # Download background music
                    logger.info(f"Downloading background music from: {background_music_url}")
                    music_data = self.download_file(background_music_url, "background music")
                    
                    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as music_file:
                        music_file.write(music_data)
                        music_path = music_file.name
                    
                    # FFmpeg command with background music
                    ffmpeg_cmd = [
                        'ffmpeg', '-y',
                        '-loop', '1', '-i', image_path,
                        '-i', audio_path,
                        '-i', music_path,
                        '-filter_complex', f'[2:a]volume={music_volume}[bg];[1:a][bg]amix=inputs=2:duration=first:dropout_transition=0[audio]',
                        '-map', '0:v', '-map', '[audio]',
                        '-c:v', 'libx264', '-preset', 'fast',
                        '-crf', str(crf), '-r', str(frame_rate),
                        '-c:a', 'aac', '-b:a', bitrate,
                        '-shortest', '-movflags', 'faststart',
                        output_path
                    ]
                else:
                    # FFmpeg command without background music
                    ffmpeg_cmd = [
                        'ffmpeg', '-y',
                        '-loop', '1', '-i', image_path,
                        '-i', audio_path,
                        '-c:v', 'libx264', '-preset', 'fast',
                        '-crf', str(crf), '-r', str(frame_rate),
                        '-c:a', 'aac', '-b:a', bitrate,
                        '-shortest', '-movflags', 'faststart',
                        output_path
                    ]
                
                logger.info("Running FFmpeg command...")
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=timeout_seconds)
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg failed: {result.stderr}")
                    raise Exception(f"Video generation failed: {result.stderr}")
                
                # Read generated video
                with open(output_path, 'rb') as f:
                    video_data = f.read()
                
                logger.info(f"Video generated successfully, size: {len(video_data)} bytes")
                return video_data
                
            finally:
                # Cleanup temporary files
                for path in [image_path, audio_path, output_path]:
                    try:
                        os.unlink(path)
                    except:
                        pass
                        
                if music_path:
                    try:
                        os.unlink(music_path)
                    except:
                        pass
        
        except subprocess.TimeoutExpired as e:
            logger.error(f"Video generation timed out")
            raise Exception(f"Video generation timed out")
        except Exception as e:
            logger.error(f"Video generation error: {str(e)}")
            raise Exception(f"Video generation failed: {str(e)}")