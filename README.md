# NovaSell Phase 3 - Authentication & CRUD

## 📋 Contenu Phase 3

✅ **Authentification JWT**
- Register avec OTP
- Login avec rate limiting IP+phone
- Refresh token (30j)
- Access token (24h)

✅ **CRUD Produits**
- Créer/Modifier/Supprimer/Lister
- Filtres: published, category, search
- Pagination

✅ **CRUD Clients**
- Créer/Modifier/Supprimer/Lister
- Stats: total orders, total spent
- Recherche par phone/nom

✅ **Middlewares**
- JWT validation automatique
- Request ID unique
- Error handling global
- Rate limiting (IP + phone)
- CORS

✅ **Security**
- Bcrypt password hashing (12 rounds)
- JWT HS256
- OTP via Twilio
- Rate limiting IP+phone (10 attempts/5min)
- Idempotency

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone le repo
git clone <repo>
cd novasell

# Crée l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Installe les dépendances
pip install -r requirements.txt

# Configure les variables d'environnement
cp .env.example .env
# Édite .env avec tes valeurs
```

### 2. Setup Base de Données

```bash
# Crée la DB (PostgreSQL doit être installé)
./scripts/setup_db.sh

# Ou manuellement:
createdb novasell_production
createuser novasell_app
psql -U postgres -d novasell_production -f migrations/init.sql

# Applique les migrations Alembic
alembic upgrade head
```

### 3. Démarre l'API

```bash
# Mode développement (avec auto-reload)
uvicorn app.main:app --reload

# L'API est disponible à: http://localhost:8000
# Docs: http://localhost:8000/api/v1/docs
# ReDoc: http://localhost:8000/api/v1/redoc
```

---

## 📚 API Endpoints Phase 3

### Authentication

```bash
# 1. Register (crée un compte + envoie OTP)
POST /api/v1/merchants/register
{
  "phone": "+237690000000",
  "name": "Boutique Awa",
  "country": "CM",
  "password": "SecurePassword123",
  "password_confirm": "SecurePassword123"
}

# 2. Verify OTP (complète l'inscription)
POST /api/v1/merchants/verify-otp
{
  "phone": "+237690000000",
  "otp": "123456"
}

# Ou en MVP: Register + Create en une requête
POST /api/v1/merchants/register-complete
{
  "phone": "+237690000000",
  "name": "Boutique Awa",
  "country": "CM",
  "password": "SecurePassword123",
  "password_confirm": "SecurePassword123"
}

# 3. Login
POST /api/v1/merchants/login
{
  "phone": "+237690000000",
  "password": "SecurePassword123"
}

Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 86400
}

# 4. Refresh Access Token
POST /api/v1/merchants/refresh-token
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}

# 5. Get Profile
GET /api/v1/merchants/profile
Header: Authorization: Bearer <access_token>

# 6. Logout
POST /api/v1/merchants/logout
Header: Authorization: Bearer <access_token>
```

### Products CRUD

```bash
# Create Product
POST /api/v1/products
Authorization: Bearer <token>
{
  "name": "Patio Decor Set",
  "description": "Beautiful outdoor furniture",
  "price_amount": 150000,
  "published": true,
  "stock": 10,
  "category": "Furniture",
  "sku": "PATIO-001",
  "image_url": "https://..."
}

# List Products
GET /api/v1/products?skip=0&limit=10&published=true&category=Furniture&search=patio
Authorization: Bearer <token>

# Get Product
GET /api/v1/products/{product_id}
Authorization: Bearer <token>

# Update Product
PUT /api/v1/products/{product_id}
Authorization: Bearer <token>
{
  "price_amount": 160000,
  "stock": 8
}

# Delete Product
DELETE /api/v1/products/{product_id}
Authorization: Bearer <token>

# Publish Product
POST /api/v1/products/{product_id}/publish
Authorization: Bearer <token>

# Unpublish Product
POST /api/v1/products/{product_id}/unpublish
Authorization: Bearer <token>
```

### Customers CRUD

```bash
# Create Customer
POST /api/v1/customers
Authorization: Bearer <token>
{
  "phone": "+237690000001",
  "name": "John Doe"
}

# List Customers
GET /api/v1/customers?skip=0&limit=10&sort_by=created_at&search=john
Authorization: Bearer <token>

# Get Customer
GET /api/v1/customers/{customer_id}
Authorization: Bearer <token>

# Update Customer
PUT /api/v1/customers/{customer_id}
Authorization: Bearer <token>
{
  "name": "John Doe Updated"
}

# Delete Customer
DELETE /api/v1/customers/{customer_id}
Authorization: Bearer <token>

# Get Customer Orders
GET /api/v1/customers/{customer_id}/orders?skip=0&limit=10
Authorization: Bearer <token>
```

---

## 🔐 Authentication Flow

```
┌─────────────────────────────────────────────────┐
│               REGISTRATION FLOW                  │
└─────────────────────────────────────────────────┘

1. POST /register
   └─> Send OTP via SMS (Twilio)
   └─> Store OTP in Redis (10 min validity)

2. POST /verify-otp
   └─> Verify OTP (max 5 attempts)
   └─> Create Merchant in DB
   └─> Return merchant data

┌─────────────────────────────────────────────────┐
│                 LOGIN FLOW                       │
└─────────────────────────────────────────────────┘

1. POST /login (phone + password)
   └─> Check rate limit (IP + phone: 10 attempts/5min)
   └─> Verify credentials (bcrypt)
   └─> Generate JWT tokens

2. Return:
   - access_token (valid 24h)
   - refresh_token (valid 30d)

┌─────────────────────────────────────────────────┐
│               TOKEN REFRESH FLOW                 │
└─────────────────────────────────────────────────┘

1. POST /refresh-token (refresh_token)
   └─> Verify refresh token
   └─> Generate new access_token

2. Use new access_token for API calls

┌─────────────────────────────────────────────────┐
│            API CALL WITH JWT                     │
└─────────────────────────────────────────────────┘

1. GET /products
   Header: Authorization: Bearer {access_token}
   └─> JWTValidationMiddleware extracts merchant_id
   └─> Middleware stores in request.state.merchant_id
   └─> Route uses merchant_id for data filtering

2. Response is filtered by merchant_id (data isolation)
```

---

## 🛡️ Rate Limiting

### Login Rate Limit
- **Limite**: 10 tentatives
- **Fenêtre**: 5 minutes
- **Clé**: IP + phone
- **Dépassement**: 429 Too Many Requests

### OTP Rate Limit
- **Limite**: 3 demandes
- **Fenêtre**: 5 minutes
- **Clé**: phone
- **Dépassement**: 429 Too Many Requests

### API Rate Limit
- **Limite**: 100 calls
- **Fenêtre**: 1 minute
- **Clé**: IP
- **Dépassement**: 429 Too Many Requests

---

## 🔒 Security Features

✅ **Password Security**
- Bcrypt hashing (12 rounds)
- Min 8 characters
- Require uppercase + numbers
- Timing-safe comparison

✅ **JWT Security**
- HS256 algorithm
- Issued by: novasell-api
- Access token: 24h
- Refresh token: 30j (for refresh only)

✅ **OTP Security**
- 6-digit numeric code
- Valid 10 minutes
- Max 5 incorrect attempts
- Sent via Twilio (SMS)

✅ **Rate Limiting**
- IP + phone combination
- Redis-backed (stateless)
- Sliding window

✅ **Data Isolation**
- Merchant data strictly filtered
- Customers belong to merchants
- Products belong to merchants
- Orders belong to merchants

---

## 📝 Logging

Tous les logs sont affichés dans la console:

```
2026-05-01 12:34:56 - app.routers.auth - INFO - Merchant registered: +237690000000
2026-05-01 12:35:10 - app.routers.auth - INFO - Merchant logged in: +237690000000
2026-05-01 12:35:20 - app.routers.products - INFO - Product created: uuid by merchant uuid
```

---

## 🧪 Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=app tests/

# Specific test
pytest tests/test_auth.py -v
```

---

## 📦 Fichiers Phase 3

```
app/
├── main.py                 # FastAPI app + lifespan
├── config.py              # Settings (JWT, OTP, etc.)
├── database.py            # SQLAlchemy setup
├── models.py              # ORM models
├── schemas.py             # Pydantic schemas
├── middlewares.py         # JWT, error handling, rate limiting
├── services/
│   └── auth_service.py    # JWT, bcrypt, OTP
├── routers/
│   ├── auth.py            # Register, login, refresh
│   ├── products.py        # CRUD products
│   └── customers.py       # CRUD customers
└── requirements.txt       # Dependencies

.env.example              # Environment template
setup_db.sh              # DB initialization script
```

---

## 🚨 Erreurs Courantes

### 1. "Cannot find module 'app'"
```bash
# Assure-toi que tu es dans le bon répertoire
pwd  # doit afficher .../novasell
# Et que le venv est activé
source venv/bin/activate
```

### 2. "PostgreSQL connection refused"
```bash
# Assure-toi que PostgreSQL est démarré
sudo systemctl start postgresql

# Ou crée manuellement:
createdb novasell_production
```

### 3. "Invalid refresh token"
```
Les refresh tokens expirent après 30 jours
Demande un nouveau login
```

### 4. "Too many login attempts"
```
Rate limit: 10 tentatives par 5 minutes (IP + phone)
Attends 5 minutes avant de réessayer
```

---

## 📞 Next Steps (Phase 4)

Phase 4 va couvrir:
- ✅ Order Management (créer, mettre à jour)
- ✅ Payment Integration (webhooks)
- ✅ Balance Calculation (ledger)
- ✅ Payout Management

---

## 🎯 Checklist Déploiement

- [ ] `.env` avec vraies valeurs (API keys, URLs)
- [ ] PostgreSQL 14+ installé et configuré
- [ ] Redis installé (pour OTP, rate limiting)
- [ ] Twilio account avec Verify service
- [ ] SSL certificate (production)
- [ ] CORS origins configurées
- [ ] SECRET_KEY changé (production)
- [ ] DEBUG=false (production)
- [ ] Log files setup

---

**Phase 3 terminée! Prêt pour Phase 4? 🚀**v