# NovaSell - Diagrammes UML Complets

## 1. Diagramme de Classes (Entités Métier)

```
┌─────────────────────────────────────────────────────────────────────┐
│                          MERCHANT (Vendeur)                         │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - phone: string (unique, E.164)                                     │
│ - name: string                                                      │
│ - country: string (ex: "CM")                                        │
│ - status: MerchantStatus (ACTIVE | SUSPENDED)                       │
│ - created_at: timestamp                                             │
│ - updated_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + getBalance(): Balance                                             │
│ + getAvailableBalance(): int                                        │
│ + requestPayout(amount): Payout                                     │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ 1..* (owns)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PRODUCT (Produit)                            │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - merchant_id: UUID (FK → Merchant)                                 │
│ - name: string                                                      │
│ - description: string                                               │
│ - price_amount: int (XOF, centimes)                                 │
│ - currency: string ("XOF")                                          │
│ - published: boolean                                                │
│ - stock: int                                                        │
│ - image_url: string (optional)                                      │
│ - category: string                                                  │
│ - sku: string                                                       │
│ - created_at: timestamp                                             │
│ - updated_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + getPrice(): int                                                   │
│ + isAvailable(qty): boolean                                         │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ 0..* (contains)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        CUSTOMER (Client)                            │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - phone: string (E.164, index)                                      │
│ - name: string (optional)                                           │
│ - merchant_id: UUID (FK → Merchant, optional)                       │
│ - created_at: timestamp                                             │
│ - updated_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + getOrders(): Order[]                                              │
│ + getTotalSpent(): int                                              │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ 0..* (places)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ORDER (Commande)                             │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - merchant_id: UUID (FK → Merchant)                                 │
│ - customer_id: UUID (FK → Customer, nullable)                       │
│ - customer_phone_snapshot: string (audit)                           │
│ - origin_city: string                                               │
│ - destination_city: string                                          │
│ - manual: boolean (true = commande manuelle)                        │
│ - status: OrderStatus                                               │
│ - subtotal_amount: int (XOF)                                        │
│ - total_amount: int (XOF)                                           │
│ - escrow_amount: int (XOF, montant en séquestre)                    │
│ - currency: string ("XOF")                                          │
│ - created_at: timestamp                                             │
│ - updated_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + confirm(): void                                                   │
│ + cancel(): void                                                    │
│ + getEscrowStatus(): EscrowStatus                                   │
│ + releaseEscrow(): void                                             │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ 1..* (contains)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ORDER_ITEM (Ligne)                            │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - order_id: UUID (FK → Order)                                       │
│ - product_id: UUID (FK → Product, nullable)                         │
│ - name_snapshot: string (audit du nom produit)                      │
│ - qty: int                                                          │
│ - unit_price_amount: int (XOF)                                      │
│ - created_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + getSubtotal(): int                                                │
└─────────────────────────────────────────────────────────────────────┘

         ┌──────────────────────┐
         │ ORDER_STATUS_HISTORY │
         ├──────────────────────┤
         │ - id: UUID (PK)      │
         │ - order_id: UUID (FK)│
         │ - from_status        │
         │ - to_status          │
         │ - actor              │
         │ - metadata: json     │
         │ - created_at         │
         └──────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        PAYMENT (Paiement)                           │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - merchant_id: UUID (FK → Merchant)                                 │
│ - order_id: UUID (FK → Order)                                       │
│ - customer_id: UUID (FK → Customer, nullable)                       │
│ - provider: PaymentProvider (ORANGE_MONEY | MTN_MONEY)              │
│ - provider_reference: string (unique)                               │
│ - status: PaymentStatus                                             │
│ - amount: int (XOF)                                                 │
│ - currency: string ("XOF")                                          │
│ - created_at: timestamp                                             │
│ - updated_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + verify(): boolean                                                 │
│ + refund(): void                                                    │
└─────────────────────────────────────────────────────────────────────┘

         │ 1..* (triggers)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LEDGER_ENTRY (Entrée Ledger)                   │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - merchant_id: UUID (FK → Merchant)                                 │
│ - order_id: UUID (FK → Order, nullable)                             │
│ - type: LedgerType                                                  │
│   • ESCROW_HOLD (+)                                                 │
│   • ESCROW_RELEASE (-)                                              │
│   • MERCHANT_CREDIT (+)                                             │
│   • PAYOUT_REQUEST (-)                                              │
│   • PAYOUT_SETTLED (0)                                              │
│   • REFUND (-)                                                      │
│ - amount: int (signé, XOF)                                          │
│ - status: LedgerStatus (PENDING | POSTED | REVERSED)                │
│ - idempotency_key: string (unique)                                  │
│ - metadata: json (optionnel)                                        │
│ - created_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + post(): void                                                      │
│ + reverse(): void                                                   │
└─────────────────────────────────────────────────────────────────────┘

         ┌────────────────────────────────────┐
         │ BALANCE (Agrégat Dérivé)           │
         ├────────────────────────────────────┤
         │ - merchant_id: UUID                │
         │ - available: int (calculé)         │
         │ - escrow: int (en séquestre)       │
         │ - pending: int (en attente)        │
         │ - total: int (sum)                 │
         └────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      PAYOUT_ACCOUNT (Compte Retrait)                │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - merchant_id: UUID (FK → Merchant)                                 │
│ - country: string ("CM")                                            │
│ - operator: PayoutOperator (ORANGE_MONEY | MTN_MONEY)               │
│ - phone: string (E.164)                                             │
│ - is_active: boolean                                                │
│ - created_at: timestamp                                             │
│ - updated_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ Constraint: MAX 2 comptes actifs par merchant                       │
├─────────────────────────────────────────────────────────────────────┤
│ + verify(): boolean                                                 │
│ + deactivate(): void                                                │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ 0..* (has)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PAYOUT (Retrait)                             │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - merchant_id: UUID (FK → Merchant)                                 │
│ - payout_account_id: UUID (FK → PayoutAccount)                      │
│ - amount: int (XOF)                                                 │
│ - status: PayoutStatus                                              │
│   • REQUESTED                                                       │
│   • PROCESSING                                                      │
│   • SETTLED                                                         │
│   • FAILED                                                          │
│   • CANCELLED                                                       │
│ - provider_reference: string (optionnel)                            │
│ - created_at: timestamp                                             │
│ - updated_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + settle(): void                                                    │
│ + fail(): void                                                      │
│ + cancel(): void                                                    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   NOTIFICATION_LOG (Log Notifications)              │
├─────────────────────────────────────────────────────────────────────┤
│ - id: UUID (PK)                                                     │
│ - merchant_id: UUID (FK → Merchant)                                 │
│ - customer_phone: string                                            │
│ - channel: string (WHATSAPP | SMS)                                  │
│ - template: string (ex: "order_shipped")                            │
│ - payload: json                                                     │
│ - status: string (PENDING | SENT | FAILED)                          │
│ - provider_reference: string (optionnel)                            │
│ - created_at: timestamp                                             │
├─────────────────────────────────────────────────────────────────────┤
│ + mark_sent(): void                                                 │
│ + mark_failed(reason): void                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Enums & Types

```
OrderStatus:
├── PAID (payé)
├── PROCESSING (en traitement)
├── SHIPPED (expédié)
├── AWAITING_CONFIRMATION (en attente confirmation client)
├── CONFIRMED (confirmée par client)
└── CANCELLED (annulée)

PaymentStatus:
├── PENDING (en attente)
├── SUCCEEDED (réussie)
├── FAILED (échouée)
└── REFUNDED (remboursée)

PaymentProvider:
├── ORANGE_MONEY
├── MTN_MONEY
└── CARD (optional)

PayoutStatus:
├── REQUESTED (demandé)
├── PROCESSING (en cours)
├── SETTLED (réglé)
├── FAILED (échoué)
└── CANCELLED (annulé)

LedgerType:
├── ESCROW_HOLD (+) - séquestre des fonds
├── ESCROW_RELEASE (-) - libération après confirmation
├── MERCHANT_CREDIT (+) - crédit vendeur
├── PAYOUT_REQUEST (-) - demande de retrait
├── PAYOUT_SETTLED (0) - retrait effectué
└── REFUND (-) - remboursement

LedgerStatus:
├── PENDING (en attente de posting)
├── POSTED (confirmé)
└── REVERSED (annulé)

MerchantStatus:
├── ACTIVE
└── SUSPENDED

PayoutOperator:
├── ORANGE_MONEY
└── MTN_MONEY
```

---

## 3. Relations Clés

```
MERCHANT 1──────────┬─────────────→ PRODUCT (owns)
                    │
                    ├─────────────→ ORDER (receives)
                    │
                    ├─────────────→ PAYMENT (processes)
                    │
                    ├─────────────→ LEDGER_ENTRY (tracks)
                    │
                    ├─────────────→ PAYOUT_ACCOUNT (has, max 2 active)
                    │
                    ├─────────────→ PAYOUT (requests)
                    │
                    └─────────────→ NOTIFICATION_LOG (sends)

ORDER ──┬───────────→ ORDER_ITEM (1..*)
        ├───────────→ PAYMENT (generates)
        ├───────────→ LEDGER_ENTRY (creates)
        ├───────────→ ORDER_STATUS_HISTORY (tracks)
        └───────────→ CUSTOMER (from)

PAYMENT ────────────→ LEDGER_ENTRY (triggers)

PAYOUT_ACCOUNT ─────→ PAYOUT (0..*)

LEDGER_ENTRY ──────→ BALANCE (aggregates into)
```

---

## 4. Flux Financier - Escrow

```
┌─────────────────────────────────────────────────────────────────┐
│ SCÉNARIO: Commande avec Confirmation Client                    │
└─────────────────────────────────────────────────────────────────┘

1. CLIENT COMMANDE
   ├─ Order créée (status: PAID)
   ├─ LEDGER: ESCROW_HOLD (+100 XOF, PENDING)
   └─ Balance: escrow = 100 XOF, available = 0 XOF

2. VENDEUR ENVOIE COLIS
   ├─ Order status: SHIPPED
   ├─ NOTIFICATION: "Colis expédié" → Client
   └─ LEDGER: toujours PENDING

3. CLIENT CONFIRME RÉCEPTION
   ├─ Order status: CONFIRMED
   ├─ LEDGER: ESCROW_RELEASE (-100 XOF, POSTED)
   ├─ LEDGER: MERCHANT_CREDIT (+100 XOF, POSTED)
   └─ Balance: escrow = 0 XOF, available = 100 XOF

4. VENDEUR DEMANDE RETRAIT
   ├─ Payout créé (amount: 100 XOF)
   ├─ LEDGER: PAYOUT_REQUEST (-100 XOF, PENDING)
   └─ Balance: available = 0 XOF, pending = 100 XOF

5. PAYOUT SUCCESSFUL
   ├─ Payout status: SETTLED
   ├─ LEDGER: PAYOUT_SETTLED (status: POSTED)
   └─ Balance: available = 0 XOF, pending = 0 XOF

┌─────────────────────────────────────────────────────────────────┐
│ LEDGER_ENTRY TABLE (Source of Truth)                           │
├─────────────────────────────────────────────────────────────────┤
│ id    │ type              │ amount  │ status  │ timestamp       │
├───────┼───────────────────┼─────────┼─────────┼─────────────────┤
│ uuid1 │ ESCROW_HOLD       │ +100    │ POSTED  │ 2026-04-30 ...  │
│ uuid2 │ ESCROW_RELEASE    │ -100    │ POSTED  │ 2026-05-02 ...  │
│ uuid3 │ MERCHANT_CREDIT   │ +100    │ POSTED  │ 2026-05-02 ...  │
│ uuid4 │ PAYOUT_REQUEST    │ -100    │ POSTED  │ 2026-05-03 ...  │
│ uuid5 │ PAYOUT_SETTLED    │   0     │ POSTED  │ 2026-05-04 ...  │
└───────┴───────────────────┴─────────┴─────────┴─────────────────┘

BALANCE (Calculated from LEDGER):
  available = SUM(amount WHERE status=POSTED AND type IN [MERCHANT_CREDIT])
            - SUM(amount WHERE status=POSTED AND type IN [PAYOUT_REQUEST])
  
  escrow    = SUM(amount WHERE status=POSTED AND type=ESCROW_HOLD)
            - SUM(amount WHERE status=POSTED AND type=ESCROW_RELEASE)
  
  pending   = SUM(amount WHERE status=PENDING)
```

---

## 5. Hiérarchie d'Héritage (si nécessaire)

```
Payment (abstract)
├── OrangeMoneyPayment
├── MTNMoneyPayment
└── CardPayment

Notification (abstract)
├── WhatsAppNotification
└── SMSNotification
```

---

## 6. Contraintes & Règles Métier

```
✓ Identifiants: UUID (v4)
✓ Téléphones: E.164 normalisé (+237...)
✓ Montants: int (centimes XOF)
✓ Idempotence: idempotency_key sur ledger_entry
✓ Audit: *_history tables pour changements critiques
✓ Payout Accounts: MAX 2 actifs par merchant
✓ Orders: Peuvent être manuelles (pas de customer_id)
✓ Ledger: Single source of truth pour finances
✓ Balance: Dérivée du ledger (jamais mise à jour directe)
```
