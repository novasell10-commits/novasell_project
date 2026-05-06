# NovaSell - Architecture Système Complète

## 1. Vue Globale (High-Level)

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│                          NOVASELL PLATFORM                            │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│    ┌──────────────┐      ┌──────────────┐      ┌──────────────┐      │
│    │   FRONTEND   │      │   BACKEND    │      │   EXTERNAL   │      │
│    │ (React/Vue)  │      │  (FastAPI)   │      │  SERVICES    │      │
│    │              │      │              │      │              │      │
│    └──────┬───────┘      └──────┬───────┘      └──────┬───────┘      │
│           │                     │                     │               │
│           │                     │                     │               │
│           └─────────────────────┼─────────────────────┘               │
│                                 │                                     │
│                    ┌────────────▼───────────┐                        │
│                    │   PostgreSQL DB        │                        │
│                    │ (All Financial Data)   │                        │
│                    └───────────────────────┘                        │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Détaillée

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND LAYER                                  │
│                     (React/Vue - Vercel/Netlify)                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────┐  ┌────────────────────────┐                │
│  │   Dashboard Pages      │  │   Admin/Config Pages   │                │
│  ├────────────────────────┤  ├────────────────────────┤                │
│  │ • Accueil              │  │ • Products Manager     │                │
│  │ • Conversations        │  │ • Orders Manager       │                │
│  │ • Produits             │  │ • Payments             │                │
│  │ • Commandes            │  │ • Solde / Ledger       │                │
│  │ • Paiements            │  │ • Payouts              │                │
│  │ • Solde                │  │ • IA Config            │                │
│  │ • Playground IA        │  │ • Skills/Knowledge     │                │
│  │ • Onboarding           │  │ • Settings             │                │
│  └────────────────────────┘  └────────────────────────┘                │
│          │                              │                              │
│          └──────────────────┬───────────┘                              │
│                             │                                          │
│                    API Calls (HTTP/REST)                              │
│                             │                                          │
└─────────────────────────────┼──────────────────────────────────────────┘
                              │
                              │
┌─────────────────────────────▼──────────────────────────────────────────┐
│                    BACKEND LAYER (FastAPI)                             │
│                      Port 8000 / VPS or Cloud                          │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    AUTH LAYER                                │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │ • JWT Token Management                                       │    │
│  │ • Phone + Password Verification                             │    │
│  │ • Session Validation                                        │    │
│  │ • Role-Based Access Control (RBAC)                          │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │               API ROUTERS (Endpoints)                        │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │                                                              │    │
│  │  ┌──────────────────┐  ┌──────────────────┐                │    │
│  │  │ AUTH ROUTER      │  │ PRODUCT ROUTER   │                │    │
│  │  ├──────────────────┤  ├──────────────────┤                │    │
│  │  │ POST /register   │  │ GET /products    │                │    │
│  │  │ POST /login      │  │ POST /products   │                │    │
│  │  │ POST /refresh    │  │ PUT /products/:id│                │    │
│  │  │ POST /logout     │  │ DELETE /products │                │    │
│  │  └──────────────────┘  └──────────────────┘                │    │
│  │                                                              │    │
│  │  ┌──────────────────┐  ┌──────────────────┐                │    │
│  │  │ ORDER ROUTER     │  │ PAYMENT ROUTER   │                │    │
│  │  ├──────────────────┤  ├──────────────────┤                │    │
│  │  │ GET /orders      │  │ GET /payments    │                │    │
│  │  │ POST /orders     │  │ POST /payments   │                │    │
│  │  │ PUT /orders/:id  │  │ GET /balance     │                │    │
│  │  │ PUT /confirm/:id │  │ POST /payout     │                │    │
│  │  │ PUT /cancel/:id  │  │ GET /payouts     │                │    │
│  │  └──────────────────┘  └──────────────────┘                │    │
│  │                                                              │    │
│  │  ┌──────────────────┐  ┌──────────────────┐                │    │
│  │  │ LEDGER ROUTER    │  │ CUSTOMER ROUTER  │                │    │
│  │  ├──────────────────┤  ├──────────────────┤                │    │
│  │  │ GET /ledger      │  │ GET /customers   │                │    │
│  │  │ GET /balance     │  │ POST /customers  │                │    │
│  │  │ (read-only)      │  │ GET /customers/:id                │    │
│  │  └──────────────────┘  └──────────────────┘                │    │
│  │                                                              │    │
│  │  ┌──────────────────┐  ┌──────────────────┐                │    │
│  │  │ WHATSAPP ROUTER  │  │ NOTIFICATION R.  │                │    │
│  │  ├──────────────────┤  ├──────────────────┤                │    │
│  │  │ POST /incoming   │  │ GET /notifications                │    │
│  │  │ POST /send       │  │ POST /send-bulk  │                │    │
│  │  │ GET /chats       │  │ GET /logs        │                │    │
│  │  │ GET /messages/:id│  └──────────────────┘                │    │
│  │  └──────────────────┘                                       │    │
│  │                                                              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │              BUSINESS LOGIC LAYER (Services)               │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ MERCHANT SERVICE                                     │  │    │
│  │  │ • Create merchant                                    │  │    │
│  │  │ • Update profile                                     │  │    │
│  │  │ • Get merchant data                                  │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ ORDER SERVICE                                        │  │    │
│  │  │ • Create order (manual/auto from WhatsApp)          │  │    │
│  │  │ • Update order status                                │  │    │
│  │  │ • Confirm order (trigger ledger)                     │  │    │
│  │  │ • Cancel order (trigger refund)                      │  │    │
│  │  │ • Calculate totals                                   │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ PAYMENT SERVICE                                      │  │    │
│  │  │ • Create payment link (Orange/MTN/Card)             │  │    │
│  │  │ • Verify payment status                              │  │    │
│  │  │ • Handle webhook (payment confirmed)                 │  │    │
│  │  │ • Process refunds                                    │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ LEDGER SERVICE ⭐ (Financial Logic)                  │  │    │
│  │  │ • Create ledger entries (idempotent)                 │  │    │
│  │  │ • Post/Reverse entries                               │  │    │
│  │  │ • Calculate balance (available/escrow/pending)       │  │    │
│  │  │ • Validate escrow release                            │  │    │
│  │  │ • Audit trail                                        │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ PAYOUT SERVICE                                       │  │    │
│  │  │ • Request payout (validate balance)                  │  │    │
│  │  │ • Process payout to Mobile Money                     │  │    │
│  │  │ • Validate payout account                            │  │    │
│  │  │ • Handle payout webhook                              │  │    │
│  │  │ • Retry logic                                        │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ WHATSAPP SERVICE (Abstraction Layer) ⭐              │  │    │
│  │  │ • Interface agnostique (Meta/Baileys/Twilio)        │  │    │
│  │  │ • Send message                                       │  │    │
│  │  │ • Receive message (webhook handler)                  │  │    │
│  │  │ • Call IA service for response                       │  │    │
│  │  │ • Update order from WhatsApp confirmation           │  │    │
│  │  │ • Rate limiting per merchant                         │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ IA SERVICE (Abstraction Layer) ⭐                    │  │    │
│  │  │ • Call external IA service (GPT-OSS/Qwen/Claude)    │  │    │
│  │  │ • Fallback to OpenAI if needed                       │  │    │
│  │  │ • Add context from RAG/Knowledge Base                │  │    │
│  │  │ • Prompt engineering & guardrails                    │  │    │
│  │  │ • Logging & monitoring                               │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │ NOTIFICATION SERVICE                                │  │    │
│  │  │ • Send WhatsApp notifications                        │  │    │
│  │  │ • Send SMS notifications                             │  │    │
│  │  │ • Queue & retry logic                                │  │    │
│  │  │ • Log all notifications                              │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │            DATA ACCESS LAYER (SQLAlchemy ORM)              │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │ • Session management                                        │    │
│  │ • Query builder                                             │    │
│  │ • Transaction handling                                      │    │
│  │ • Connection pooling                                        │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                 │                                    │
└─────────────────────────────────┼────────────────────────────────────┘
                                  │
                                  │
         ┌────────────────────────┼────────────────────────────┐
         │                        │                            │
┌────────▼─────────────┐  ┌──────▼──────────┐  ┌─────────────▼────┐
│  PostgreSQL DB       │  │  MESSAGE QUEUE  │  │  EXTERNAL APIS   │
│   (Production)       │  │  (Redis/Celery) │  │                  │
├──────────────────────┤  ├─────────────────┤  ├──────────────────┤
│ • merchant           │  │ • Send SMS      │  │ • IA Service     │
│ • customer           │  │ • Send Email    │  │ • Payment        │
│ • product            │  │ • Send Push     │  │   Providers      │
│ • order              │  │ • Retry failed  │  │   (Orange/MTN)   │
│ • order_item         │  │ • Batch process │  │ • WhatsApp API   │
│ • payment            │  │                 │  │ • RAG/Vector DB  │
│ • ledger_entry       │  │                 │  │ • Storage (S3)   │
│ • payout             │  │                 │  │                  │
│ • payout_account     │  │                 │  │                  │
│ • notification_log   │  │                 │  │                  │
│ • *_history          │  │                 │  │                  │
└──────────────────────┘  └─────────────────┘  └──────────────────┘
```

---

## 3. Flux de Données - Commande Complète

```
┌────────────────────────────────────────────────────────────────────────┐
│              FLUX COMPLET: CLIENT COMMANDE → PAYOUT                    │
└────────────────────────────────────────────────────────────────────────┘

1️⃣  CLIENT ENVOIE MESSAGE WHATSAPP
    ┌─────────────────────────────────────────┐
    │ WhatsApp: "Je veux commander Pack A"    │
    └─────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Backend: POST /whatsapp/incoming               │
    │ • Webhook du provider Meta/Twilio              │
    │ • Extracte message + phone + timestamp         │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ WhatsApp Service (Abstraction)                 │
    │ • Parse message                                │
    │ • Valide merchant + rate limit                 │
    │ • Appelle IA Service pour intent/response      │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ IA Service (External)                          │
    │ • Décode intent: "ORDER"                       │
    │ • Détecte produit: "Pack A"                    │
    │ • Génère réponse chatbot                       │
    │ Returns: {intent, product_id, response}        │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Order Service                                  │
    │ • Crée Order (status: PAID, manual: false)     │
    │ • Ajoute OrderItem (Pack A, qty=1)             │
    │ • Calcule subtotal + total                     │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Ledger Service                                 │
    │ • Crée LEDGER: ESCROW_HOLD (+50000 XOF)        │
    │ • Status: POSTED                               │
    │ • Idempotency: prevent duplicates              │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ WhatsApp Service                               │
    │ • Envoie confirmation au client                │
    │ • "Votre commande est confirmée! ID: CMD-001"  │
    │ • Notifie vendor                               │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Payment Service                                │
    │ • Génère payment link (Orange Money)           │
    │ • Envoie lien au client par WhatsApp           │
    │ • Status: PENDING                              │
    └────────────────────────────────────────────────┘

2️⃣  CLIENT PAIE (Orange Money)
    ┌─────────────────────────────────────────┐
    │ Client envoie argent via Orange Money   │
    └─────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Payment Webhook (Orange Money)                 │
    │ POST /payments/webhook/orange                  │
    │ • Signature verification                       │
    │ • Extract: amount, ref, status                 │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Payment Service                                │
    │ • Valide idempotency (prevent double charge)   │
    │ • Update Payment status: SUCCEEDED             │
    │ • Match avec Order                             │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Notification Service                           │
    │ • Send WhatsApp: "Paiement reçu! Merci"        │
    │ • Notify vendor: "Paiement confirmé"           │
    │ • Log notification                             │
    └────────────────────────────────────────────────┘

3️⃣  VENDEUR EXPÉDIE COLIS
    ┌────────────────────────────────────────────────┐
    │ Vendeur dans Dashboard                         │
    │ • Clic: "Marquer comme expédié" (CMD-001)      │
    │ PUT /orders/CMD-001                            │
    │ • {status: "SHIPPED"}                          │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Order Service                                  │
    │ • Update Order.status = SHIPPED                │
    │ • Create OrderStatusHistory entry              │
    │ • Trigger notification                         │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Notification Service                           │
    │ • Send WhatsApp: "Colis expédié! Suivi: ..."   │
    │ • Template: order_shipped                      │
    └────────────────────────────────────────────────┘

4️⃣  CLIENT CONFIRME RÉCEPTION (WhatsApp ou Dashboard)
    ┌────────────────────────────────────────────────┐
    │ WhatsApp: "Confirmé, j'ai reçu"                │
    │ OU                                             │
    │ Dashboard: Clic "Confirmer réception"          │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Order Service                                  │
    │ PUT /orders/CMD-001/confirm                    │
    │ • Status: CONFIRMED                            │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ ⭐ LEDGER SERVICE (ESCROW RELEASE)              │
    │ • ESCROW_RELEASE (-50000 XOF, POSTED)          │
    │ • MERCHANT_CREDIT (+50000 XOF, POSTED)         │
    │ • Transaction DB unique                        │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Balance Recalculation                          │
    │ • available: 50000 XOF (was 0)                 │
    │ • escrow: 0 XOF (was 50000)                    │
    └────────────────────────────────────────────────┘

5️⃣  VENDEUR DEMANDE RETRAIT
    ┌────────────────────────────────────────────────┐
    │ Dashboard: "Retirer 50000 XOF"                 │
    │ POST /payouts                                  │
    │ • {amount: 50000, account_id: "uuid"}          │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Payout Service                                 │
    │ • Valide balance >= amount                     │
    │ • Crée Payout (status: REQUESTED)              │
    │ • Validate PayoutAccount                       │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ ⭐ LEDGER SERVICE (PAYOUT REQUEST)              │
    │ • PAYOUT_REQUEST (-50000 XOF, PENDING)         │
    │ • Idempotency key                              │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Balance Update                                 │
    │ • available: 0 XOF (was 50000)                 │
    │ • pending: 50000 XOF (en attente)              │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Queue Worker / Async Task                      │
    │ • Appelle API Orange Money pour retrait        │
    │ • Envoie request avec phone + amount           │
    │ • Attend confirmation                          │
    └────────────────────────────────────────────────┘

6️⃣  PAYOUT SUCCESSFUL
    ┌────────────────────────────────────────────────┐
    │ Orange Money Webhook                           │
    │ POST /payouts/webhook/orange                   │
    │ • Status: SETTLED                              │
    │ • Provider Reference: OM-123456                │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Payout Service                                 │
    │ • Update Payout.status = SETTLED               │
    │ • Idempotency check (prevent double)           │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ ⭐ LEDGER SERVICE (PAYOUT SETTLED)              │
    │ • PAYOUT_SETTLED (status: POSTED)              │
    │ • Mark PAYOUT_REQUEST as complete              │
    └────────────────────────────────────────────────┘
                        │
                        ▼
    ┌────────────────────────────────────────────────┐
    │ Balance Final                                  │
    │ • available: 0 XOF                             │
    │ • pending: 0 XOF                               │
    │ • escrow: 0 XOF                                │
    │ ✓ Cycle complet!                              │
    └────────────────────────────────────────────────┘

LEDGER_ENTRY TABLE (Audit Trail):
┌──────┬──────────────────┬────────┬────────┬──────────────┐
│ id   │ type             │ amount │ status │ timestamp    │
├──────┼──────────────────┼────────┼────────┼──────────────┤
│ 1    │ ESCROW_HOLD      │ 50000  │ POSTED │ 13:42:10     │
│ 2    │ ESCROW_RELEASE   │ -50000 │ POSTED │ 16:22:15     │
│ 3    │ MERCHANT_CREDIT  │ 50000  │ POSTED │ 16:22:16     │
│ 4    │ PAYOUT_REQUEST   │ -50000 │ POSTED │ 17:05:30     │
│ 5    │ PAYOUT_SETTLED   │ 0      │ POSTED │ 17:45:22     │
└──────┴──────────────────┴────────┴────────┴──────────────┘
```

---

## 4. WhatsApp Service - Abstraction (Scalable Provider Swapping)

```
┌────────────────────────────────────────────────────────────────┐
│           WHATSAPP SERVICE - PROVIDER AGNOSTIC                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Interface (Abstract):                                         │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ class WhatsAppProvider(ABC):                         │    │
│  │   @abstractmethod                                    │    │
│  │   async def send_message(phone, text, media): ...   │    │
│  │                                                      │    │
│  │   @abstractmethod                                    │    │
│  │   async def webhook_handler(payload): ...           │    │
│  │                                                      │    │
│  │   @abstractmethod                                    │    │
│  │   async def get_status(provider_msg_id): ...        │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Implementations:                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ MetaWhatsAppProvider                                 │    │
│  │ • Uses Meta Official API                             │    │
│  │ • Phone number + access token                        │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ BaileysWhatsAppProvider                              │    │
│  │ • Uses Baileys (Node.js)                             │    │
│  │ • Chrome automation / QR code                        │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ EvolutionAPIProvider                                 │    │
│  │ • Uses Evolution API (Docker)                        │    │
│  │ • HTTP endpoints                                     │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ TwilioWhatsAppProvider                               │    │
│  │ • Uses Twilio Conversations API                      │    │
│  │ • Managed service                                    │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Service Factory:                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ class WhatsAppService:                               │    │
│  │   def __init__(provider_type: str):                 │    │
│  │     if provider_type == "META":                      │    │
│  │       self.provider = MetaWhatsAppProvider()        │    │
│  │     elif provider_type == "BAILEYS":                 │    │
│  │       self.provider = BaileysWhatsAppProvider()     │    │
│  │     ...                                              │    │
│  │                                                      │    │
│  │   async def send_message(phone, text):              │    │
│  │     return await self.provider.send_message(...)    │    │
│  │                                                      │    │
│  │   async def receive_message(payload):               │    │
│  │     return await self.provider.webhook_handler(...) │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Config (env variables):                                       │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ WHATSAPP_PROVIDER=META                               │    │
│  │ META_PHONE_ID=123456789                              │    │
│  │ META_ACCESS_TOKEN=xxx                                │    │
│  │                                                      │    │
│  │ # To switch to Baileys:                              │    │
│  │ WHATSAPP_PROVIDER=BAILEYS                            │    │
│  │ BAILEYS_CHROME_PATH=/path/to/chrome                 │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Switching Providers (1 change):                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ # Before: Baileys                                    │    │
│  │ whatsapp = WhatsAppService("BAILEYS")               │    │
│  │                                                      │    │
│  │ # After: Meta Official API (same code!)             │    │
│  │ whatsapp = WhatsAppService("META")                  │    │
│  │                                                      │    │
│  │ # Rest of code unchanged ✓                           │    │
│  └──────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. IA Service - Abstraction (Pluggable LLM Providers)

```
┌────────────────────────────────────────────────────────────────┐
│           IA SERVICE - LLM PROVIDER AGNOSTIC                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Interface (Abstract):                                         │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ class AIProvider(ABC):                               │    │
│  │   @abstractmethod                                    │    │
│  │   async def generate_response(                       │    │
│  │     message: str,                                    │    │
│  │     context: dict,                                   │    │
│  │     merchant_id: str                                 │    │
│  │   ) -> AIResponse:                                   │    │
│  │     """                                              │    │
│  │     Returns: {                                       │    │
│  │       response_text: str,                            │    │
│  │       intent: str,                                   │    │
│  │       confidence: float,                             │    │
│  │       product_id?: str,                              │    │
│  │       metadata: dict                                 │    │
│  │     }                                                │    │
│  │     """                                              │    │
│  │                                                      │    │
│  │   @abstractmethod                                    │    │
│  │   async def rag_search(                              │    │
│  │     query: str,                                      │    │
│  │     merchant_id: str                                 │    │
│  │   ) -> str:  # context from KB                       │    │
│  │     """Fetch relevant docs from Knowledge Base"""    │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Implementations:                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ExternalAIProvider (Collègue's Service)              │    │
│  │ • Call collègue's FastAPI endpoint                   │    │
│  │ • POST /ai/generate {message, context}              │    │
│  │ • Uses GPT-OSS-20B or Qwen3-VL-30B                  │    │
│  │ • Fallback to local RAG                              │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ OpenAIProvider (Fallback)                            │    │
│  │ • Uses OpenAI API (GPT-4o)                           │    │
│  │ • Reliable backup                                    │    │
│  │ • Higher cost but battle-tested                      │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ LocalLLMProvider (Future)                            │    │
│  │ • Uses Ollama or self-hosted Llama 2                 │    │
│  │ • Zero cost but slower                               │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Service Factory with Fallback:                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ class AIService:                                     │    │
│  │   def __init__(primary: str, fallback: str):        │    │
│  │     self.primary = self._create_provider(primary)   │    │
│  │     self.fallback = self._create_provider(fallback) │    │
│  │                                                      │    │
│  │   async def generate_response(msg, ctx, merchant):  │    │
│  │     try:                                             │    │
│  │       return await self.primary.generate_response() │    │
│  │     except Exception as e:                           │    │
│  │       logger.warning(f"Primary AI failed: {e}")     │    │
│  │       return await self.fallback.generate_response()│    │
│  │                                                      │    │
│  │   async def rag_search(query, merchant_id):         │    │
│  │     # Try collègue's service first                  │    │
│  │     # Fall back to local if timeout                 │    │
│  │     return await self.primary.rag_search(...)       │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Config:                                                       │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ # Primary: Collègue's service                        │    │
│  │ AI_PRIMARY_PROVIDER=EXTERNAL                         │    │
│  │ AI_EXTERNAL_URL=https://ai.example.com:8000         │    │
│  │ AI_EXTERNAL_TIMEOUT=5s                               │    │
│  │                                                      │    │
│  │ # Fallback: OpenAI                                   │    │
│  │ AI_FALLBACK_PROVIDER=OPENAI                          │    │
│  │ OPENAI_API_KEY=sk-...                                │    │
│  │                                                      │    │
│  │ # RAG                                                │    │
│  │ PINECONE_API_KEY=xxx                                 │    │
│  │ PINECONE_INDEX=novasell-kb                           │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  Switching Providers (same interface!):                        │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ # Before: Collègue's service                         │    │
│  │ ai = AIService(                                      │    │
│  │   primary="EXTERNAL",                               │    │
│  │   fallback="OPENAI"                                  │    │
│  │ )                                                    │    │
│  │                                                      │    │
│  │ # After: Direct OpenAI (if collègue abandonne)      │    │
│  │ ai = AIService(                                      │    │
│  │   primary="OPENAI",                                  │    │
│  │   fallback="LOCAL"                                   │    │
│  │ )                                                    │    │
│  │                                                      │    │
│  │ # Rest of code: ZERO changes ✓                       │    │
│  │ response = await ai.generate_response(msg, ctx)     │    │
│  └──────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
```

---

## 6. Deployment Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    PRODUCTION DEPLOYMENT                      │
└───────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────┐
│       CloudFlare / DNS               │
│  novasell.cm (custom domain)         │
│  api.novasell.cm                     │
└────────────┬────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────┐
│           Cloud Provider (AWS / Digital Ocean / Render)      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Frontend (Static)                                     │ │
│  │ • Vercel or Netlify                                   │ │
│  │ • React/Vue SPA                                       │ │
│  │ • Auto-deploy from git                                │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Backend Container (Docker)                            │ │
│  │ ┌─────────────────────────────────────────────────┐   │ │
│  │ │ FastAPI App (Python)                            │   │ │
│  │ │ • Uvicorn ASGI server                           │   │ │
│  │ │ • 4-8 worker processes                          │   │ │
│  │ │ • Health checks                                 │   │ │
│  │ │ • Metrics (Prometheus)                          │   │ │
│  │ └─────────────────────────────────────────────────┘   │ │
│  │ Port: 8000 (internal)                                 │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ PostgreSQL Database                                   │ │
│  │ • Managed RDS (AWS) or DBaaS                          │ │
│  │ • Automated backups                                   │ │
│  │ • Read replicas for scaling                           │ │
│  │ • Connection pooling (pgBouncer)                      │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Redis (Message Queue / Cache)                         │ │
│  │ • Celery workers for async tasks                      │ │
│  │ • SMS/Email sending                                   │ │
│  │ • Rate limiting cache                                 │ │
│  │ • Session store                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Load Balancer (Nginx / HAProxy)                       │ │
│  │ • Reverse proxy                                       │ │
│  │ • SSL/TLS termination                                 │ │
│  │ • Rate limiting                                       │ │
│  │ • Gzip compression                                    │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
             │
             │ (HTTPS)
             │
┌────────────▼──────────────────────────────────────────┐
│         EXTERNAL SERVICES                             │
├───────────────────────────────────────────────────────┤
│                                                       │
│ ┌──────────────────┐  ┌──────────────────┐           │
│ │ Meta WhatsApp    │  │ Orange/MTN Money │           │
│ │ Cloud API        │  │ Payment Gateway  │           │
│ │ (sending msgs)   │  │ (payouts)        │           │
│ └──────────────────┘  └──────────────────┘           │
│                                                       │
│ ┌──────────────────┐  ┌──────────────────┐           │
│ │ IA Service       │  │ S3 / Cloudinary  │           │
│ │ (Collègue)       │  │ (images storage) │           │
│ └──────────────────┘  └──────────────────┘           │
│                                                       │
│ ┌──────────────────┐  ┌──────────────────┐           │
│ │ Pinecone/RAG     │  │ OpenAI (fallback)│           │
│ │ (Knowledge base) │  │ (IA fallback)    │           │
│ └──────────────────┘  └──────────────────┘           │
│                                                       │
└───────────────────────────────────────────────────────┘
```

---

## 7. Monitoring & Logging

```
┌──────────────────────────────────────────────────────────────┐
│               MONITORING & OBSERVABILITY STACK                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Logging (ELK Stack / Datadog / CloudWatch)             │ │
│  │ • All API requests (with request_id)                   │ │
│  │ • All ledger operations (audit trail)                  │ │
│  │ • Payment webhook events                               │ │
│  │ • IA service calls & latencies                         │ │
│  │ • Errors & exceptions                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Metrics (Prometheus + Grafana)                          │ │
│  │ • API latency (p50, p95, p99)                          │ │
│  │ • Request rate (RPS)                                   │ │
│  │ • Error rate (5xx, 4xx)                                │ │
│  │ • DB connection pool usage                             │ │
│  │ • Queue depth (Redis)                                  │ │
│  │ • Ledger posting success rate                          │ │
│  │ • Payout settlement rate                               │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Alerts (PagerDuty / Opsgenie)                           │
│  │ • IA service timeout                                    │ │
│  │ • Payment provider down                                 │ │
│  │ • DB connection pool exhausted                          │ │
│  │ • Ledger posting failures                               │ │
│  │ • WhatsApp rate limit exceeded                          │ │
│  │ • High error rate detected                              │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Distributed Tracing (Jaeger / Zipkin)                   │ │
│  │ • Trace a single request through all services           │ │
│  │ • Identify bottlenecks                                  │ │
│  │ • Visualize service dependencies                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 8. Security Considerations

```
┌──────────────────────────────────────────────────────────────┐
│                     SECURITY LAYERS                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ✓ HTTPS/TLS (All traffic encrypted)                         │
│ ✓ JWT Auth (Stateless, signed tokens)                       │
│ ✓ Phone Verification (OTP before account creation)          │
│ ✓ Rate Limiting (Per merchant, per IP)                      │
│ ✓ Webhook Signature Verification (Orange/MTN)               │
│ ✓ Idempotency Keys (Prevent double charges)                 │
│ ✓ SQL Injection Protection (SQLAlchemy ORM)                 │
│ ✓ CORS (Frontend domain whitelist)                          │
│ ✓ CSRF (Token validation for POST/PUT/DELETE)               │
│ ✓ Sensitive Data Masking (Phone numbers, payments)          │
│ ✓ Audit Logs (All financial transactions logged)            │
│ ✓ Secrets Management (.env / Vault for credentials)         │
│ ✓ Database Encryption (At rest + in transit)                │
│ ✓ Regular Security Audits (OWASP Top 10)                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

