import json, os, sqlite3
from pathlib import Path
import httpx
from fastapi import HTTPException
from models import State

KEY=os.getenv('REDIS_KEY_PREFIX','inventory:v1')+':state'
LUA="""local old=redis.call('GET',KEYS[1]); local version=0; if old then version=cjson.decode(old).version end; if version~=tonumber(ARGV[1]) then return 0 end; redis.call('SET',KEYS[1],ARGV[2]); return 1"""

class Store:
    def __init__(self):
        self.url=os.getenv('UPSTASH_REDIS_REST_URL','').rstrip('/')
        self.token=os.getenv('UPSTASH_REDIS_REST_TOKEN','')
        if bool(self.url)!=bool(self.token):
            raise HTTPException(503,'Set both Upstash REST URL and REST TOKEN')
        self.remote=bool(self.url and self.token)
        if os.getenv('VERCEL') and not self.remote:
            raise HTTPException(503,'Upstash credentials are required on Vercel. Console URL is not a REST URL.')
        self.path=Path(os.getenv('LOCAL_DB_PATH',str(Path(__file__).parent/'data/inventory.sqlite3')))
        if not self.remote:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.db() as c: c.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
    def db(self): return sqlite3.connect(self.path,timeout=15)
    async def command(self,*args):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r=await client.post(self.url,json=list(args),headers={'Authorization':'Bearer '+self.token})
                r.raise_for_status(); result=r.json()
                if result.get('error'): raise ValueError('Redis command failed')
                return result.get('result')
        except Exception:
            raise HTTPException(503,'Redis connection failed. Check REST credentials and database availability.')
    async def read(self):
        if self.remote: value=await self.command('GET',KEY)
        else:
            with self.db() as c:
                row=c.execute('SELECT value FROM state WHERE id=1').fetchone();value=row[0] if row else None
        return State.model_validate_json(value) if value else State()
    async def save(self,state,expected):
        state.version=expected+1
        value=state.model_dump_json()
        if len(value.encode())>3500000: raise HTTPException(413,'Database export exceeds app limit; archive old records before continuing.')
        if self.remote: ok=await self.command('EVAL',LUA,1,KEY,expected,value)
        else:
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT value FROM state WHERE id=1').fetchone()
                old=json.loads(row[0])['version'] if row else 0
                ok=old==expected
                if ok:c.execute('INSERT OR REPLACE INTO state VALUES (1,?)',(value,))
        if not ok: raise HTTPException(409,'Data changed in another tab. Refresh and try again; your changes were not saved.')
        return state
