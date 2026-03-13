from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON
from app.database import Base


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id = Column(String, primary_key=True)
    query = Column(Text, nullable=False)
    status = Column(String, default="pending")  # pending/running/completed/failed
    sub_queries = Column(JSON)
    sources_raw = Column(JSON)
    report = Column(JSON)
    agent_events = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_time_ms = Column(Integer, nullable=True)
    sources_searched = Column(Integer, default=0)
    sources_used = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
