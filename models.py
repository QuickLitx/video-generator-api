from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class VideoGeneration(db.Model):
    __tablename__ = 'video_generations'
    
    id = db.Column(db.Integer, primary_key=True)
    image_url = db.Column(db.String(500), nullable=False)
    audio_url = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='completed')
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<VideoGeneration {self.id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'image_url': self.image_url,
            'audio_url': self.audio_url,
            'status': self.status,
            'file_size': self.file_size,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
