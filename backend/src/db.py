import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
url = os.environ['DATABASE_URL']
engine = create_engine(url, pool_pre_ping=True, **({'isolation_level': 'READ COMMITTED'} if url.startswith('mysql') else {}))
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
def db_session():
    with Session() as s:
        yield s
