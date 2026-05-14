# Tech Stack & Authentication Analysis

## 🏗️ TECH STACK

### **Backend**
- **Framework**: Flask (Python web framework)
- **CORS**: Flask-CORS (for cross-origin requests)
- **Data Processing**: 
  - pandas (data manipulation)
  - yfinance (stock/crypto data)
  - requests (HTTP calls)
- **Server**: Flask development server (can be deployed to Heroku, Railway, etc.)

### **Frontend**
- **Framework**: React 19.2.0
- **Language**: TypeScript
- **Build Tool**: Vite 7.2.4
- **Routing**: React Router DOM 7.13.0
- **HTTP Client**: Axios 1.13.3
- **Animation**: Framer Motion 12.29.2
- **Charts**: Lightweight Charts 4.2.0
- **Styling**: Tailwind CSS 3.4.17
- **Package Manager**: npm

### **Deployment Files**
- **Procfile**: For Heroku deployment
- **runtime.txt**: Specifies Python version for deployment

---

## 🔐 AUTHENTICATION & USER DATA STORAGE

### **Is User Data Getting Stored?**
**YES**, user data IS being stored, BUT with a critical limitation.

### **Where is it Stored?**

#### **❌ Backend Storage (Temporary - Not Persistent)**
```python
# Location: app.py, Line 15
users_db = {}  # Simple in-memory Python dictionary
```

**Storage Details:**
- User data is stored in **RAM (Random Access Memory)** as a Python dictionary
- Data includes:
  - `email`: User email address
  - `fullname`: User's full name
  - `password`: Password (stored in plain text - **SECURITY ISSUE**)
  - `registered_at`: Registration timestamp

**Example stored structure:**
```python
users_db = {
  "user@email.com": {
    "fullname": "John Doe",
    "password": "mypassword123",
    "registered_at": "2026-01-28T10:30:45.123456"
  }
}
```

#### **⚠️ CRITICAL ISSUE: Data Loss on Server Restart**
- When the Flask server restarts, ALL user data is **LOST PERMANENTLY**
- This is NOT suitable for production
- All previous registrations/logins will be gone

#### **✅ Frontend Storage (Client-Side)**
```typescript
// Location: HomeAuthPage.tsx, Line 68
localStorage.setItem('user', JSON.stringify(result.user))
```

**Storage Details:**
- After successful login/register, user data is stored in **Browser's LocalStorage**
- Persists even after browser closes
- Stored data:
  - `email`
  - `fullname`

---

## 🔑 Authentication Flow

### **1. Registration Flow**
```
User enters: fullname, email, password
    ↓
Frontend → POST /api/auth/register
    ↓
Backend checks if email exists in users_db
    ↓
If new: Stores in users_db + Returns success
    ↓
Frontend stores user in localStorage
    ↓
Navigates to /backtesting page
```

### **2. Login Flow**
```
User enters: email, password
    ↓
Frontend → POST /api/auth/login
    ↓
Backend checks users_db for matching email/password
    ↓
If found & password matches: Returns success
    ↓
Frontend stores user in localStorage
    ↓
Navigates to /backtesting page
```

### **3. Logout Flow**
```
User clicks logout
    ↓
Frontend removes user from localStorage
    ↓
Redirects to home page
```

---

## 🚨 SECURITY ISSUES

1. **Plain Text Passwords**: Passwords stored without hashing
   - Should use bcrypt/argon2

2. **In-Memory Storage**: Data lost on restart
   - Need: Database (PostgreSQL, MongoDB, etc.)

3. **No JWT/Sessions**: No token-based authentication
   - Should use JWT tokens for secure API calls

4. **No Encryption**: Sensitive data not encrypted
   - Should use HTTPS in production

5. **localStorage**: Client-side storage vulnerable to XSS attacks
   - Need: Secure HTTP-only cookies

---

## 📋 What Gets Stored Where

| Data | Backend Storage | Frontend Storage | Persistence |
|------|-----------------|------------------|-------------|
| Email | ✅ users_db | ✅ localStorage | ❌ Lost on restart / ✅ Persists |
| Fullname | ✅ users_db | ✅ localStorage | ❌ Lost on restart / ✅ Persists |
| Password | ✅ users_db (plain) | ❌ No | ❌ Lost on restart |
| Login State | ❌ No | ✅ localStorage | ✅ Persists |

---

## 🔄 Current Endpoints

- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `POST /api/auth/logout` - Logout user
- `GET /api/test-auth` - Check auth status
- `GET /api/candles` - Get stock/crypto data
- `GET /api/search_symbol` - Search for symbols

---

## 💡 Recommendations for Production

1. **Replace in-memory storage with a real database**
   ```python
   # Use PostgreSQL with SQLAlchemy ORM
   from flask_sqlalchemy import SQLAlchemy
   ```

2. **Hash passwords before storing**
   ```python
   from werkzeug.security import generate_password_hash
   password_hash = generate_password_hash(password)
   ```

3. **Implement JWT authentication**
   ```python
   from flask_jwt_extended import JWTManager
   ```

4. **Use secure cookies instead of localStorage**
   ```python
   response.set_cookie('user_token', token, httponly=True, secure=True)
   ```

5. **Add rate limiting to prevent brute force**
   ```python
   from flask_limiter import Limiter
   ```

6. **Validate and sanitize all inputs**
   ```python
   # Use werkzeug validators or marshmallow
   ```

---

## 📊 Summary

**Current State**: ✅ Functional for development/demo, ❌ Not production-ready

- **Frontend**: Modern React/TypeScript setup - ✅ Good
- **Backend**: Basic Flask setup - ⚠️ Needs database
- **Authentication**: Working but insecure - ⚠️ Critical fixes needed
- **Data Storage**: In-memory only - ❌ Not persistent
