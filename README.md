# Video Generator API

Aplicație Flask pentru generarea de video-uri verticale din imagine și audio, optimizată pentru social media (Instagram Reels, TikTok).

## Funcționalități

- Generare video vertical 1080x1920 din imagine statică și audio
- Suport pentru background music cu volum configurabil
- Salvare locală cu URL-uri directe de acces
- Endpoint de activare pentru automatizare Make
- Optimizat pentru deployment gratuit pe Render

## Endpoint-uri

### `/startup` (POST)
Verifică și activează aplicația din automatizare Make.

```json
{
  "status": "started",
  "message": "Application is now ready for requests",
  "ready_for_video_generation": true
}
```

### `/generate-video` (POST)
Generează video din imagine și audio.

**Request:**
```json
{
  "image_url": "https://example.com/image.jpg",
  "audio_url": "https://example.com/audio.mp3",
  "background_music_url": "https://example.com/music.mp3",
  "width": 1080,
  "height": 1920,
  "music_volume": 0.06
}
```

**Response:**
```json
{
  "video_url": "https://your-app.com/static/videos/video_20250616_123456.mp4",
  "file_size": 1234567,
  "timestamp": "20250616_123456"
}
```

## Deployment pe Render

1. Fork acest repository
2. Conectează la Render.com
3. Creează Web Service cu:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn --bind 0.0.0.0:$PORT main:app`
4. Adaugă PostgreSQL database
5. Configurează Environment Variables:
   - `DATABASE_URL` (din PostgreSQL)
   - `SESSION_SECRET` (string random)

## Cerințe de sistem

- Python 3.11+
- FFmpeg
- PostgreSQL
- Dependențe din requirements.txt

## Dezvoltare locală

```bash
pip install -r requirements.txt
python main.py
```

Aplicația va rula pe `http://localhost:5000`