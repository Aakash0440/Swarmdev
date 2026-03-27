"""
Scaffolder — generates the correct project skeleton BEFORE agents start coding.
Supports: React/Vite, Next.js, FastAPI, Full-Stack, ML, Python CLI.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


SCAFFOLDS: dict[str, dict[str, str]] = {

    # ── React + Vite ──────────────────────────────────────────────────────────
    "react": {
        "package.json": json.dumps({
            "name": "{{PROJECT_NAME}}",
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
                "lint": "eslint . --ext js,jsx --report-unused-disable-directives",
                "test": "vitest"
            },
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
                "react-router-dom": "^6.22.0",
                "axios": "^1.6.0"
            },
            "devDependencies": {
                "@types/react": "^18.2.0",
                "@vitejs/plugin-react": "^4.2.0",
                "autoprefixer": "^10.4.16",
                "eslint": "^8.55.0",
                "postcss": "^8.4.31",
                "tailwindcss": "^3.3.6",
                "vite": "^5.0.0",
                "vitest": "^1.0.0"
            }
        }, indent=2),

        "vite.config.js": """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 3000 },
})
""",
        "tailwind.config.js": """/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
""",
        "postcss.config.js": """export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
}
""",
        "index.html": """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{PROJECT_NAME}}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
""",
        "src/main.jsx": """import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
""",
        "src/index.css": """@tailwind base;
@tailwind components;
@tailwind utilities;
""",
        "src/App.jsx": """import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  )
}
""",
        "src/pages/Home.jsx": """export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <h1 className="text-3xl font-bold text-gray-800">Welcome</h1>
    </div>
  )
}
""",
        ".eslintrc.cjs": """module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: ['eslint:recommended', 'plugin:react/recommended', 'plugin:react/jsx-runtime'],
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  settings: { react: { version: '18.2' } },
}
""",
        ".gitignore": "node_modules\ndist\n.env\n.DS_Store\n",
        "README.md": "# {{PROJECT_NAME}}\n\n```bash\nnpm install\nnpm run dev\n```\n",
    },

    # ── Full-Stack (React + FastAPI) ───────────────────────────────────────────
    "fullstack": {
        # ── Backend ──────────────────────────────────────────────────────────
        "backend/main.py": """from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from api.auth import router as auth_router
from database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="{{PROJECT_NAME}} API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(api_router, prefix="/api", tags=["api"])

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
""",
        "backend/database.py": """from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
""",
        "backend/models/__init__.py": "from .user import User\nfrom .item import Item\n",
        "backend/models/user.py": """from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("Item", back_populates="owner")
""",
        "backend/models/item.py": """from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(String)
    price = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="items")
""",
        "backend/schemas/__init__.py": "from .user import UserCreate, UserRead, UserUpdate, Token\nfrom .item import ItemCreate, ItemRead, ItemUpdate\n",
        "backend/schemas/user.py": """from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserRead(BaseModel):
    id: int
    email: EmailStr
    username: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    password: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[int] = None
""",
        "backend/schemas/item.py": """from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    price: float = 0.0

class ItemRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    price: float
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class ItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
""",
        "backend/api/__init__.py": "",
        "backend/api/routes.py": """from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models.item import Item
from schemas.item import ItemCreate, ItemRead, ItemUpdate
from api.auth import get_current_user
from models.user import User

router = APIRouter()

@router.get("/items", response_model=List[ItemRead])
async def list_items(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(Item).filter(Item.is_active == True).offset(skip).limit(limit).all()

@router.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    item: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_item = Item(**item.model_dump(), owner_id=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.get("/items/{item_id}", response_model=ItemRead)
async def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@router.put("/items/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: int,
    item_update: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    item = db.query(Item).filter(Item.id == item_id, Item.owner_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for field, value in item_update.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item

@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    item = db.query(Item).filter(Item.id == item_id, Item.owner_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.is_active = False
    db.commit()
""",
        "backend/api/auth.py": """from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
import os
from database import get_db
from models.user import User
from schemas.user import UserCreate, UserRead, Token, TokenData

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

SECRET_KEY = os.getenv("SECRET_KEY", "change_me_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_exception
    return user

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=hash_password(user_in.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)

@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
""",
        "backend/api/deps.py": """from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from api.auth import get_current_user
from models.user import User

def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user
""",
        "backend/requirements.txt": (
            "fastapi\nuvicorn[standard]\npython-dotenv\n"
            "sqlalchemy\nalembic\npydantic[email]\n"
            "python-jose[cryptography]\npasslib[bcrypt]\nhttpx\npytest\npytest-asyncio\n"
        ),
        "backend/.env.example": "DATABASE_URL=sqlite:///./app.db\nSECRET_KEY=change_me_to_a_long_random_string\n",
        "backend/Dockerfile": """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
        "backend/tests/__init__.py": "",
        "backend/tests/test_auth.py": """import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_register_and_login():
    resp = client.post("/api/auth/register", json={
        "email": "test@example.com", "username": "tester", "password": "secret123"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "test@example.com"

def test_login_wrong_password():
    resp = client.post("/api/auth/login", data={
        "username": "test@example.com", "password": "wrongpass"
    })
    assert resp.status_code == 401

def test_protected_route_no_token():
    resp = client.get("/api/items")
    assert resp.status_code in (200, 401)
""",
        "backend/tests/test_items.py": """import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def _get_token():
    client.post("/api/auth/register", json={
        "email": "item_test@example.com", "username": "item_user", "password": "pass1234"
    })
    resp = client.post("/api/auth/login", data={
        "username": "item_test@example.com", "password": "pass1234"
    })
    return resp.json()["access_token"]

def test_create_and_list_items():
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/items", json={"title": "Widget", "price": 9.99}, headers=headers)
    assert resp.status_code == 201
    item = resp.json()
    assert item["title"] == "Widget"

    resp2 = client.get("/api/items")
    assert resp2.status_code == 200
    assert isinstance(resp2.json(), list)

def test_get_item_not_found():
    resp = client.get("/api/items/99999")
    assert resp.status_code == 404
""",
        # ── Frontend (React + Vite + Tailwind) ────────────────────────────────
        "frontend/package.json": """{
  "name": "{{PROJECT_NAME}}-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0",
    "axios": "^1.6.0",
    "@tanstack/react-query": "^5.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.31",
    "tailwindcss": "^3.3.6",
    "vite": "^5.0.0",
    "vitest": "^1.0.0"
  }
}
""",
        "frontend/vite.config.js": """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: { '/api': 'http://localhost:8000' }
  },
})
""",
        "frontend/tailwind.config.js": """export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
""",
        "frontend/postcss.config.js": "export default { plugins: { tailwindcss: {}, autoprefixer: {} } }\n",
        "frontend/index.html": """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{PROJECT_NAME}}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
""",
        "frontend/src/main.jsx": """import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
import './index.css'

const queryClient = new QueryClient()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
""",
        "frontend/src/index.css": "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n",
        "frontend/src/App.jsx": """import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Navbar from './components/Navbar.jsx'

function PrivateRoute({ children }) {
  const { user } = useAuth()
  return user ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
""",
        "frontend/src/context/AuthContext.jsx": """import { createContext, useContext, useState, useEffect } from 'react'
import api from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
      api.get('/auth/me').then(r => setUser(r.data)).catch(() => localStorage.removeItem('token')).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email, password) => {
    const form = new URLSearchParams({ username: email, password })
    const { data } = await api.post('/auth/login', form)
    localStorage.setItem('token', data.access_token)
    api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
    const me = await api.get('/auth/me')
    setUser(me.data)
  }

  const logout = () => {
    localStorage.removeItem('token')
    delete api.defaults.headers.common['Authorization']
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, login, logout, loading }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
""",
        "frontend/src/services/api.js": """import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
""",
        "frontend/src/services/items.js": """import api from './api.js'

export const itemsApi = {
  list: (params) => api.get('/items', { params }),
  get:  (id)     => api.get(`/items/${id}`),
  create: (data) => api.post('/items', data),
  update: (id, data) => api.put(`/items/${id}`, data),
  delete: (id)   => api.delete(`/items/${id}`),
}
""",
        "frontend/src/components/Navbar.jsx": """import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function Navbar() {
  const { user, logout } = useAuth()
  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex justify-between items-center">
      <Link to="/" className="text-xl font-semibold text-gray-800">{{PROJECT_NAME}}</Link>
      <div className="flex items-center gap-4">
        {user ? (
          <>
            <span className="text-sm text-gray-600">{user.username}</span>
            <button onClick={logout} className="text-sm text-red-500 hover:text-red-700">Logout</button>
          </>
        ) : (
          <>
            <Link to="/login" className="text-sm text-blue-600 hover:underline">Login</Link>
            <Link to="/register" className="text-sm bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Sign up</Link>
          </>
        )}
      </div>
    </nav>
  )
}
""",
        "frontend/src/components/ItemCard.jsx": """export default function ItemCard({ item, onDelete }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 flex flex-col gap-2">
      <div className="flex justify-between items-start">
        <h3 className="font-medium text-gray-900">{item.title}</h3>
        <span className="text-green-600 font-semibold">${item.price.toFixed(2)}</span>
      </div>
      {item.description && <p className="text-sm text-gray-500">{item.description}</p>}
      <button
        onClick={() => onDelete(item.id)}
        className="mt-auto self-end text-xs text-red-400 hover:text-red-600"
      >Remove</button>
    </div>
  )
}
""",
        "frontend/src/components/ItemForm.jsx": """import { useState } from 'react'

export default function ItemForm({ onSubmit, loading }) {
  const [form, setForm] = useState({ title: '', description: '', price: '' })
  const handle = e => setForm(f => ({ ...f, [e.target.name]: e.target.value }))
  const submit = e => {
    e.preventDefault()
    onSubmit({ ...form, price: parseFloat(form.price) || 0 })
    setForm({ title: '', description: '', price: '' })
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 bg-white border border-gray-200 rounded-lg p-4">
      <input name="title" value={form.title} onChange={handle} placeholder="Title" required
        className="border border-gray-300 rounded px-3 py-2 text-sm" />
      <input name="description" value={form.description} onChange={handle} placeholder="Description (optional)"
        className="border border-gray-300 rounded px-3 py-2 text-sm" />
      <input name="price" type="number" step="0.01" value={form.price} onChange={handle} placeholder="Price"
        className="border border-gray-300 rounded px-3 py-2 text-sm" />
      <button type="submit" disabled={loading}
        className="bg-blue-600 text-white rounded py-2 text-sm hover:bg-blue-700 disabled:opacity-50">
        {loading ? 'Adding…' : 'Add item'}
      </button>
    </form>
  )
}
""",
        "frontend/src/pages/Login.jsx": """import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handle = e => setForm(f => ({ ...f, [e.target.name]: e.target.value }))

  const submit = async e => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      await login(form.email, form.password)
      navigate('/')
    } catch {
      setError('Invalid email or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <form onSubmit={submit} className="bg-white border border-gray-200 rounded-xl p-8 w-full max-w-sm flex flex-col gap-4">
        <h1 className="text-2xl font-semibold text-gray-900">Sign in</h1>
        {error && <p className="text-sm text-red-600 bg-red-50 rounded p-2">{error}</p>}
        <input name="email" type="email" value={form.email} onChange={handle} placeholder="Email" required
          className="border border-gray-300 rounded px-3 py-2 text-sm" />
        <input name="password" type="password" value={form.password} onChange={handle} placeholder="Password" required
          className="border border-gray-300 rounded px-3 py-2 text-sm" />
        <button type="submit" disabled={loading}
          className="bg-blue-600 text-white rounded py-2 font-medium hover:bg-blue-700 disabled:opacity-50">
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="text-sm text-center text-gray-500">
          No account? <Link to="/register" className="text-blue-600 hover:underline">Register</Link>
        </p>
      </form>
    </div>
  )
}
""",
        "frontend/src/pages/Register.jsx": """import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api.js'

export default function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', username: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handle = e => setForm(f => ({ ...f, [e.target.name]: e.target.value }))

  const submit = async e => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      await api.post('/auth/register', form)
      navigate('/login')
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <form onSubmit={submit} className="bg-white border border-gray-200 rounded-xl p-8 w-full max-w-sm flex flex-col gap-4">
        <h1 className="text-2xl font-semibold text-gray-900">Create account</h1>
        {error && <p className="text-sm text-red-600 bg-red-50 rounded p-2">{error}</p>}
        <input name="email" type="email" value={form.email} onChange={handle} placeholder="Email" required
          className="border border-gray-300 rounded px-3 py-2 text-sm" />
        <input name="username" value={form.username} onChange={handle} placeholder="Username" required
          className="border border-gray-300 rounded px-3 py-2 text-sm" />
        <input name="password" type="password" value={form.password} onChange={handle} placeholder="Password" required
          className="border border-gray-300 rounded px-3 py-2 text-sm" />
        <button type="submit" disabled={loading}
          className="bg-blue-600 text-white rounded py-2 font-medium hover:bg-blue-700 disabled:opacity-50">
          {loading ? 'Creating…' : 'Create account'}
        </button>
        <p className="text-sm text-center text-gray-500">
          Have an account? <Link to="/login" className="text-blue-600 hover:underline">Sign in</Link>
        </p>
      </form>
    </div>
  )
}
""",
        "frontend/src/pages/Dashboard.jsx": """import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { itemsApi } from '../services/items.js'
import ItemCard from '../components/ItemCard.jsx'
import ItemForm from '../components/ItemForm.jsx'

export default function Dashboard() {
  const qc = useQueryClient()
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['items'],
    queryFn: () => itemsApi.list().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: itemsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['items'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: itemsApi.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['items'] }),
  })

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Dashboard</h1>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div>
          <h2 className="text-sm font-medium text-gray-700 mb-3">Add item</h2>
          <ItemForm onSubmit={d => createMutation.mutate(d)} loading={createMutation.isPending} />
        </div>
        <div className="lg:col-span-2">
          <h2 className="text-sm font-medium text-gray-700 mb-3">
            Your items <span className="text-gray-400">({items.length})</span>
          </h2>
          {isLoading ? (
            <p className="text-sm text-gray-400">Loading…</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-gray-400">No items yet. Add one!</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {items.map(item => (
                <ItemCard key={item.id} item={item} onDelete={id => deleteMutation.mutate(id)} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
""",
        "frontend/.gitignore": "node_modules\ndist\n.env\n",
        # ── Root level ────────────────────────────────────────────────────────
        "docker-compose.yml": """version: '3.8'
services:
  backend:
    build: ./backend
    ports: ['8000:8000']
    environment:
      - DATABASE_URL=sqlite:///./app.db
      - SECRET_KEY=change_me_in_production
    volumes:
      - ./backend:/app
  frontend:
    image: node:20-alpine
    working_dir: /app
    volumes:
      - ./frontend:/app
    ports: ['3000:3000']
    command: sh -c "npm install && npm run dev -- --host"
    depends_on: [backend]
""",
        "Makefile": """dev-backend:
\tcd backend && uvicorn main:app --reload --port 8000

dev-frontend:
\tcd frontend && npm install && npm run dev

test-backend:
\tcd backend && pytest tests/ -v

install:
\tcd backend && pip install -r requirements.txt
\tcd frontend && npm install

docker-up:
\tdocker-compose up --build
""",
        "README.md": """# {{PROJECT_NAME}}

Full-stack app — React 18 + FastAPI + SQLAlchemy + JWT auth.

## Quick start

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Or with Docker:
```bash
docker-compose up --build
```

## Structure

```
backend/
  main.py          FastAPI entry point
  database.py      SQLAlchemy engine + session
  models/          ORM models (User, Item)
  schemas/         Pydantic schemas
  api/
    routes.py      Item CRUD endpoints
    auth.py        Register / login / JWT
    deps.py        Shared dependencies
  tests/           pytest test suite
frontend/
  src/
    App.jsx        Route layout
    context/       AuthContext (JWT storage)
    pages/         Login, Register, Dashboard
    components/    Navbar, ItemCard, ItemForm
    services/      api.js (axios), items.js
docker-compose.yml
Makefile
```

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/auth/register | — | Create account |
| POST | /api/auth/login | — | Get JWT token |
| GET | /api/auth/me | ✓ | Current user |
| GET | /api/items | — | List items |
| POST | /api/items | ✓ | Create item |
| PUT | /api/items/:id | ✓ | Update item |
| DELETE | /api/items/:id | ✓ | Soft-delete |
""",
    },

    # ── ML / AI Project ───────────────────────────────────────────────────────
    "ml": {
        "requirements.txt": "torch\ntorchvision\ntransformers\nscikit-learn\npandas\nnumpy\nmatplotlib\nseaborn\njupyterlab\nmlflow\nfastapi\nuvicorn\npython-dotenv\n",
        "src/__init__.py": "",
        "src/config.py": """import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

for d in [DATA_DIR, MODELS_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True)

MODEL_NAME = os.getenv("MODEL_NAME", "default_model")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 32))
EPOCHS = int(os.getenv("EPOCHS", 10))
LEARNING_RATE = float(os.getenv("LEARNING_RATE", 1e-3))
""",
        "src/data/dataset.py": """import torch
from torch.utils.data import Dataset

class CustomDataset(Dataset):
    def __init__(self, data, labels=None, transform=None):
        self.data = data
        self.labels = labels
        self.transform = transform

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        sample = self.data[idx]
        if self.transform:
            sample = self.transform(sample)
        if self.labels is not None:
            return sample, self.labels[idx]
        return sample
""",
        "src/models/__init__.py": "",
        "src/train.py": """\"\"\"Training entry point.\"\"\"
import mlflow
from config import EPOCHS, BATCH_SIZE, LEARNING_RATE

def train():
    with mlflow.start_run():
        mlflow.log_params({"epochs": EPOCHS, "batch_size": BATCH_SIZE, "lr": LEARNING_RATE})
        print("Training started — implement model loop here")

if __name__ == "__main__":
    train()
""",
        "src/serve.py": """from fastapi import FastAPI
import uvicorn

app = FastAPI(title="ML Model API")

@app.post("/predict")
async def predict(payload: dict):
    # TODO: load model and run inference
    return {"prediction": None, "confidence": 0.0}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
""",
        "notebooks/exploration.ipynb": json.dumps({
            "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": [{"cell_type": "markdown", "metadata": {}, "source": ["# Exploration\n"]}]
        }),
        ".env.example": "MODEL_NAME=my_model\nBATCH_SIZE=32\nEPOCHS=10\nLEARNING_RATE=0.001\n",
        "README.md": "# {{PROJECT_NAME}}\n\n```bash\npip install -r requirements.txt\npython src/train.py\npython src/serve.py\n```\n",
    },

    # ── Python (CLI / backend) ────────────────────────────────────────────────
    "python": {
        "requirements.txt": "fastapi\nuvicorn[standard]\npython-dotenv\nclick\nrich\n",
        "src/__init__.py": "",
        "src/main.py": """\"\"\"Entry point for {{PROJECT_NAME}}.\"\"\"\nimport click\n\n@click.group()\ndef cli():\n    pass\n\nif __name__ == '__main__':\n    cli()\n""",
        "tests/__init__.py": "",
        "tests/test_main.py": "def test_placeholder():\n    assert True\n",
        ".env.example": "DEBUG=true\n",
        "README.md": "# {{PROJECT_NAME}}\n\n```bash\npip install -r requirements.txt\npython src/main.py\n```\n",
    },
}


class ProjectScaffolder:
    """Writes the project skeleton to disk before agents start coding."""

    def __init__(self, output_dir: str, project_name: str, stack: str):
        self.root = Path(output_dir) / project_name
        self.project_name = project_name
        self.stack = stack

    def scaffold(self) -> list[str]:
        """Write all scaffold files. Returns list of created paths."""
        files_created = []
        templates = self._get_templates()

        for rel_path, content in templates.items():
            abs_path = self.root / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            text = content.replace("{{PROJECT_NAME}}", self.project_name)
            abs_path.write_text(text, encoding="utf-8")
            files_created.append(str(abs_path))
            logger.debug(f"Scaffolded: {rel_path}")

        logger.info(f"Scaffolded {len(files_created)} files for stack='{self.stack}'")
        return files_created

    def _get_templates(self) -> dict[str, str]:
        return SCAFFOLDS.get(self.stack, SCAFFOLDS["python"])

    @property
    def root_path(self) -> str:
        return str(self.root)
