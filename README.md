# 🩸 Blood Management System (BMS)

An enterprise-grade, full-stack **Blood Management and Emergency Broadcast System** designed to streamline voluntary blood donations, manage blood bank inventory with cold-chain traceability, process hospital blood requests with automated compatibility reservation, enforce laboratory infectious disease screening, and coordinate life-saving **Emergency SOS** donor broadcasts during critical shortages.

---

## 📑 Table of Contents
1. [Project Overview](#-project-overview)
2. [System Architecture & Tech Stack](#-system-architecture--tech-stack)
3. [Key Features & Modules](#-key-features--modules)
4. [Role-Based Access Control (RBAC) Matrix](#-role-based-access-control-rbac-matrix)
5. [How This Project Was Implemented](#-how-this-project-was-implemented)
6. [System Requirements](#-system-requirements)
7. [Installation & Setup Guide](#-installation--setup-guide)
8. [Email & SMTP Configuration](#-email--smtp-configuration)
9. [Running Tests & Quality Assurance](#-running-tests--quality-assurance)
10. [API Reference & Documentation](#-api-reference--documentation)
11. [Project Directory Structure](#-project-directory-structure)

---

## 🌟 Project Overview

The **Blood Management System** bridges the gap between voluntary donors, blood banks, testing laboratories, and hospitals. It replaces error-prone manual spreadsheets with a secure, real-time platform that guarantees:
- **Donor Safety & Eligibility**: Strict 90-day intervals, weight thresholds, and age limits.
- **Traceability & Safety**: Individual unit tracking from donation, 5-panel laboratory screening (HIV, Hep B, Hep C, Syphilis, Malaria), to hospital transfusion or safe disposal.
- **Rapid Emergency Response**: Automated Emergency SOS broadcast engine calculating geographic donor proximity (Haversine formula) and red blood cell compatibility to alert eligible donors during critical inventory deficits.

---

## 🛠 System Architecture & Tech Stack

```
                                  ┌────────────────────────┐
                                  │   React / Vite / SSR   │
                                  │  (TanStack, Radix UI)  │
                                  └───────────┬────────────┘
                                              │  HTTPS / JWT
                                  ┌───────────▼────────────┐
                                  │   Django REST Framework │
                                  │  (RBAC & Simple JWT)   │
                                  └─────┬────────────┬─────┘
                     ┌──────────────────┼────────────┼──────────────────┐
                     │                  │            │                  │
           ┌─────────▼────────┐┌────────▼───────┐┌───▼────────────┐┌────▼─────────────┐
           │ Accounts / RBAC  ││ Donors & Camps ││ Inventory & QC ││ Emergency SOS &  │
           │ & JWT Auth       ││ & Donations    ││ & Requests     ││ Notifications    │
           └──────────────────┘└────────────────┘└────────────────┘└──────────────────┘
                                        │
                              ┌─────────▼─────────┐
                              │  SQLite / RDBMS   │
                              └───────────────────┘
```

### Backend:
- **Framework**: Django 5.1 & Django REST Framework (DRF)
- **Authentication**: JWT via `djangorestframework-simplejwt`
- **API Documentation**: OpenAPI 3.0 via `drf-spectacular` (Swagger UI & ReDoc)
- **CORS Handling**: `django-cors-headers`
- **Database**: SQLite (local development) / PostgreSQL ready
- **Email Service**: Dual-mode (Django Console backend for local testing, SMTP / Gmail App Password for live delivery)

### Frontend:
- **Framework**: React 18 with Vite (Nitro SSR / SPA build)
- **Routing**: `@tanstack/react-router`
- **Data Fetching**: `@tanstack/react-query` & custom centralized API client
- **UI & Styling**: Tailwind CSS, Radix UI primitives, Lucide React icons
- **Notifications**: Sonner toast notification system

---

## 🚀 Key Features & Modules

### 1. 🔐 Authentication & Session Security
- Dual identifier login (authenticate using either **username** or **email**).
- JWT architecture with access tokens ($60\text{ min}$) and refresh tokens ($7\text{ days}$).
- Concurrent 401 request queue interceptor for transparent background token refreshing.
- Role-aware frontend route protection preventing unauthorized access.

### 2. 👤 Donor Profile & Eligibility Engine
- Medical profiling: blood group, date of birth, body weight, last donation date, and medical notes.
- **Automated Eligibility Engine**:
  - Minimum 90 days interval between full blood donations.
  - Body weight $\ge 50\text{ kg}$.
  - Age between 18 and 65 years.
  - Active deferral validation.

### 3. 📦 Blood Inventory & Traceability
- Individual Blood Unit tracking with auto-generated unique identifiers (`BLD-YYYYMMDD-XXXX`).
- Automated status lifecycle: `TESTING` $\rightarrow$ `AVAILABLE` $\rightarrow$ `RESERVED` $\rightarrow$ `DISPATCHED` / `DISCARDED` (with strict 42-day RBC expiry validation).
- Expiry date monitoring with visual low-stock alerts and quarantine isolation.

### 4. 🔬 Testing & Quality Control (Lab QC)
- Mandatory 5-panel infectious disease screening:
  1. **HIV** (Human Immunodeficiency Virus)
  2. **Hepatitis B** (HBsAg)
  3. **Hepatitis C** (Anti-HCV)
  4. **Syphilis** (VDRL/RPR)
  5. **Malaria** (Parasite screen)
- **Atomic Safety Gate**: Any reactive/positive result immediately discards the unit. Only units with all 5 negative markers are promoted to `AVAILABLE`.

### 5. 🏥 Hospital Blood Requests & Fulfillment
- Hospital staff can submit blood requests with urgency levels (`NORMAL`, `HIGH`, `CRITICAL`) and patient reference.
- Blood Bank Admins review available stock, perform compatibility checks, and atomically approve/reserve stock or reject requests with audit logs.

### 6. 🏕 Donation Camps & Voluntary Drives
- Blood banks publish upcoming public donation drives with target collection quotas, venues, and timings.
- Donors reserve slots with duplicate registration prevention.

### 7. 🔔 In-App Notifications & Professional Communications
- Database-backed in-app inbox categorized by `EMERGENCY`, `REQUEST`, `INVENTORY`, `CAMP`, and `SYSTEM`.
- Unread count badge updated in real time on the top navigation bar.
- Multi-recipient dispatch with HTML email templates.

### 8. 🚨 Emergency SOS & Blood Broadcast System
- Triggered for critical pending requests during local inventory deficits.
- **Geographic Proximity Engine**: Computes distance using the Haversine formula across donor coordinates.
- **RBC Compatibility Matrix**:
  - `O-`: Universal red cell donor (can donate to all groups).
  - `AB+`: Universal red cell recipient.
- Instant alert broadcast via in-app notifications and email dispatch.
- Audit trail for targeted donors and broadcast cancellation with mandatory reasons.

---

## 👥 Role-Based Access Control (RBAC) Matrix

| Feature / Endpoint | `SUPER_ADMIN` | `BLOOD_BANK_ADMIN` | `HOSPITAL_STAFF` | `LAB_TECHNICIAN` | `DONOR` |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **System User Management** (`/api/users/`) | ✅ Full | ❌ | ❌ | ❌ | ❌ |
| **Blood Bank Management** (`/api/blood-banks/`) | ✅ Full | ✅ View/Edit Own | ❌ | ❌ | ❌ |
| **Inventory & Units** (`/api/blood-units/`) | ✅ Full | ✅ Own Bank | ❌ | ❌ | ❌ |
| **Record Test Results** (`/api/test-results/`) | ✅ Full | ✅ View Own | ❌ | ✅ Record/Update | ❌ |
| **Blood Requests** (`/api/blood-requests/`) | ✅ View All | ✅ Approve/Reject | ✅ Create/View Own | ❌ | ❌ |
| **Schedule Camps** (`/api/donation-camps/`) | ✅ Full | ✅ Create/Manage | ❌ | ❌ | ✅ View/Register |
| **Emergency SOS Broadcast** (`/api/sos/`) | ✅ Full | ✅ Trigger/Cancel | ❌ | ❌ | ❌ |
| **Donation History** (`/api/donations/`) | ✅ Full | ✅ Record Collection | ❌ | ❌ | ✅ Own History |
| **Notifications** (`/api/notifications/`) | ✅ Own | ✅ Own | ✅ Own | ✅ Own | ✅ Own |

---

## 🏗 How This Project Was Implemented

The project followed a disciplined, test-driven, multi-phase engineering approach:

1. **Step 1 — Foundation & Authentication**:
   - Custom User model extending `AbstractUser` with 5 distinct `UserRole` choices.
   - JWT authentication (`/api/auth/login/`, `/api/auth/register/`, `/api/auth/me/`, `/api/auth/token/refresh/`).
2. **Step 2 — RBAC & User Administration**:
   - Granular permission classes (`IsSuperAdmin`, `IsBloodBankAdmin`, `IsHospitalStaff`, `IsLabTechnician`, `IsDonor`).
3. **Step 3 — Donor Management & Eligibility**:
   - Donor profiles, blood group enumeration, and eligibility rule validation engine.
4. **Step 4 — Blood Inventory & Traceability**:
   - `BloodBank` and `BloodUnit` models with FIFO stock management, unique unit identifiers, and inventory summary views.
5. **Step 5 — Testing & Quality Control (QC)**:
   - Atomic state transitions evaluating 5-disease screening panels to clear or discard units.
6. **Step 6 — Blood Requests & Hospital Integration**:
   - Hospital request submission, urgency workflows, and transactional stock reservation.
7. **Step 7 — Donations & Donation Camps**:
   - Public drive scheduling, capacity counters, and voluntary donation history logging.
8. **Step 8 — Notifications & Communications**:
   - Multi-channel notification dispatch with database inbox and HTML email support.
9. **Step 9 — Profile Management**:
   - User profile endpoints, local media file storage, and avatar management.
10. **Step 10 — Emergency SOS Broadcast**:
    - Haversine proximity filtering, RBC compatibility logic, and shortage broadcast coordination.
11. **Steps 11A to 11C — Frontend Integration**:
    - Integration with centralized Axios-like Fetch client, token refresh queues, and real Django endpoints while strictly preserving Lovable UI design.
12. **Step 12 — Final Integration & Verification**:
    - Comprehensive verification across 268 automated tests, zero TypeScript errors, and zero Django issues.

---

## 💻 System Requirements

- **Python**: Version `3.10`, `3.11`, or `3.12`
- **Node.js**: Version `18.x` or `20.x` (with `npm`)
- **Git**: Installed and available in PATH
- **Operating System**: Windows, Linux, or macOS

---

## ⚙️ Installation & Setup Guide

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/blood-mgmt.git
cd blood-mgmt
```

---

### 2. Backend Setup (Django)

1. **Create and activate a virtual environment**:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy the example environment file:
   - **Windows (PowerShell)**:
     ```powershell
     Copy-Item .env.example .env
     ```
   - **Linux / macOS**:
     ```bash
     cp .env.example .env
     ```

4. **Apply Database Migrations**:
   ```bash
   python manage.py migrate
   ```

5. **Start the Django Development Server**:
   ```bash
   python manage.py runserver
   ```
   *The backend API will be live at `http://localhost:8000/`.*

---

### 3. Frontend Setup (React / Vite)

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install Node dependencies**:
   ```bash
   npm install
   ```

3. **Start the Vite development server**:
   ```bash
   npm run dev
   ```
   *The frontend application will be live at `http://localhost:8080/` (or `http://localhost:5173/`).*

---

## 📧 Email & SMTP Configuration

The system supports two email modes configured in `.env`:

### A. Development Mode (Default)
In development (`DEBUG=True`), Django automatically uses the **Console Email Backend**. Outgoing emails (notifications, SOS alerts, password resets) are printed directly to the terminal stdout without sending live network packets.

### B. Production / Gmail SMTP Mode
To send live emails using a Gmail address:
1. Enable 2-Step Verification on your Google Account.
2. Generate an **App Password** (16 characters) from [Google Account Security](https://myaccount.google.com/apppasswords).
3. Update your `.env` file:
   ```ini
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_USE_SSL=False
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-16-char-app-password
   DEFAULT_FROM_EMAIL=Blood Management System <your-email@gmail.com>
   ```

> [!NOTE]
> No Google Cloud projects, service accounts, or GCP credentials are required. Standard SMTP is used.

---

## 🧪 Running Tests & Quality Assurance

### Run Complete Backend Test Suite (268 Tests)
```bash
python manage.py test
```
*Expected output: `Ran 268 tests ... OK` (0 failures, 0 errors).*

### Run Django System Check
```bash
python manage.py check
```

### Validate Frontend TypeScript (0 Errors)
```bash
cd frontend
npx tsc --noEmit
```

### Build Frontend Production Bundle
```bash
cd frontend
npm run build
```

---

## 📖 API Reference & Documentation

When the Django backend server is running, interactive API documentation is available at:
- **Swagger UI**: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
- **ReDoc**: [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)
- **OpenAPI Schema (JSON/YAML)**: [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)

### Core Endpoint Summary

| Module | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `/api/auth/login/` | Obtain JWT access and refresh token pair |
| **Auth** | `POST` | `/api/auth/register/` | Register donor or hospital staff user |
| **Auth** | `GET` | `/api/auth/me/` | Fetch current authenticated user session |
| **Auth** | `POST` | `/api/auth/token/refresh/` | Refresh expired access token |
| **Profile** | `GET/PATCH` | `/api/profile/` | View / update personal user profile |
| **Profile** | `POST/DELETE` | `/api/profile/image/` | Upload / delete profile avatar |
| **Donors** | `GET/PATCH` | `/api/donors/me/` | Retrieve / update donor medical attributes |
| **Donors** | `GET` | `/api/donors/me/eligibility/` | Evaluate donor 90-day eligibility rules |
| **Inventory** | `GET` | `/api/inventory/summary/` | Stock distribution summary by blood group |
| **Inventory** | `GET` | `/api/blood-units/` | List traceable individual blood units |
| **QC Testing** | `GET/POST` | `/api/test-results/` | List and record 5-panel lab screening results |
| **Requests** | `GET/POST` | `/api/blood-requests/` | List and create hospital blood requests |
| **Requests** | `POST` | `/api/blood-requests/<id>/approve/` | Approve request and reserve blood units |
| **Requests** | `POST` | `/api/blood-requests/<id>/reject/` | Reject blood request |
| **Camps** | `GET/POST` | `/api/donation-camps/` | List and schedule donation camps |
| **Camps** | `POST` | `/api/donation-camps/<id>/register/` | Register voluntary donor for camp slot |
| **Donations** | `GET/POST` | `/api/donations/` | List and record blood donations |
| **Notifications**| `GET` | `/api/notifications/` | In-app notification inbox |
| **Notifications**| `GET` | `/api/notifications/unread-count/` | Unread notifications count badge |
| **Emergency SOS**| `POST` | `/api/blood-requests/<pk>/sos/` | Trigger Emergency SOS broadcast |
| **Emergency SOS**| `GET` | `/api/sos/` | List emergency broadcasts |
| **Emergency SOS**| `GET` | `/api/sos/<id>/recipients/` | Audit targeted donors & email logs |
| **Emergency SOS**| `POST` | `/api/sos/<id>/cancel/` | Cancel active emergency broadcast |

---

## 📁 Project Directory Structure

```
blood-mgmt/
├── manage.py                     # Django management CLI
├── requirements.txt              # Python package dependencies
├── .env.example                  # Environment variable template
├── .gitignore                    # Git ignore configuration
├── config/                       # Project configuration & settings
│   ├── settings.py               # Django settings (JWT, CORS, SMTP, DRF)
│   ├── urls.py                   # Root URL routing & OpenAPI registration
│   └── wsgi.py                   # WSGI application entrypoint
├── apps/                         # Backend business domain modules
│   ├── accounts/                 # Custom User model, JWT Auth, RBAC
│   ├── common/                   # Shared utilities & health endpoints
│   ├── donors/                   # Donor profiles & eligibility engine
│   ├── inventory/                # Blood banks, blood units, stock tracking
│   ├── testing_qc/               # Lab disease screening & clearance
│   ├── blood_requests/           # Hospital requests & stock reservation
│   ├── donations/                # Donation history & donation camps
│   ├── notifications/            # In-app inbox & email dispatch
│   └── emergency_sos/            # Emergency broadcast & radius matching
└── frontend/                     # React / Vite SPA frontend
    ├── package.json              # Node dependencies
    ├── vite.config.ts            # Vite & Nitro build config
    └── src/
        ├── components/           # UI components, layout, badges, charts
        ├── hooks/                # React custom hooks
        ├── lib/                  # TypeScript types, token storage, utils
        ├── providers/            # AuthProvider & TanStack Query Provider
        ├── routes/               # TanStack file-based application routes
        └── services/             # API services connecting to Django
```

---

## 🛡 License

This project is developed for educational and healthcare demonstration purposes under the [MIT License](LICENSE).
