# KE-JANI Frontend Authentication Guide (React + Vite)

This guide details how the frontend team should integrate with the KE-JANI Authentication API. The API uses JSON Web Tokens (JWT) for authentication and includes various Role-Based Access Controls (RBAC) covering Landlords, Property Managers, and Tenants.

## Base URL

All API requests in your Vite app should point to the backend URL.
Assuming you configure Vite `proxy` or `.env` variables:

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

---

## 1. Authentication Flow & Token Management

We use `djangorestframework-simplejwt`. Upon successful login, you receive an `access` token (expires in 1 hour) and a `refresh` token (expires in 7 days).

### Best Practices for React:

1. **Store Tokens Securely:** Store the `access` and `refresh` tokens in `localStorage` or `sessionStorage` (or memory/HttpOnly cookies if you prefer).
2. **Axios Interceptors:** Create an Axios instance that automatically attaches the `Authorization: Bearer <access_token>` header to every request, and intercepts `401 Unauthorized` errors to automatically attempt to refresh the token.

### Example Axios Interceptor:

```javascript
import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

// Request Interceptor (Attach Token)
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Response Interceptor (Refresh Token on 401)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If 401 and not a retry yet (to avoid infinite loops)
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshToken = localStorage.getItem("refresh_token");
        const res = await axios.post(
          `${import.meta.env.VITE_API_BASE_URL}/auth/token/refresh/`,
          {
            refresh: refreshToken,
          },
        );

        // Save new tokens
        localStorage.setItem("access_token", res.data.access);
        if (res.data.refresh) {
          localStorage.setItem("refresh_token", res.data.refresh); // Rotation enabled
        }

        // Retry original request
        originalRequest.headers["Authorization"] = `Bearer ${res.data.access}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh token expired or invalid -> Force logout
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  },
);

export default api;
```

---

## 2. API Endpoints & Expected Status Codes

### Universal Status Codes to Handle

- **200 OK / 201 Created**: Success.
- **400 Bad Request**: Validation errors. The response body will contain field-specific errors, e.g., `{"email": ["A user with this email already exists."], "id_number": ["National ID must be 7-8 digits."]}`.
- **401 Unauthorized**: Invalid or missing token, or unverified email at login.
- **403 Forbidden**: User does not have the correct role (e.g., Tenant trying to create a Property Manager), OR a **Demo User** trying to mutate data (`POST/PUT/PATCH/DELETE`).
- **404 Not Found**: E.g., bad invitation or verification tokens.
- **429 Too Many Requests**: Rate limits exceeded (e.g. >10 logins per minute).

---

### A. Registration

**1. Landlord Registration**

- **POST** `/auth/register/landlord/`
- **Body:** `first_name`, `last_name`, `id_number`, `estimated_properties` ("1-10", "11-30", etc.), `email`, `phone`, `subscription_tier`, `password`, `password_confirm`, `terms_agreed` (boolean).
- **Success (201):** `{"message": "Registration successful..."}` (They must verify email).
- **Failure (400):** Validation errors (e.g. Duplicate email).

**2. Property Manager Registration**

- **POST** `/auth/register/pm/`
- **Body:** Similar to Landlord, requires `commission_rate`, `company_name` (optional), `id_number`.

**3. Validate Invitations (GET)**
When users click an email invite link, they land on a frontend page like `/invite?token=UUID`. Fetch this to grab pre-filled info.

- **GET** `/auth/register/pm/validate-invite/?token=<uuid>` (Returns 200 with invited_email, invited_name, etc. OR 404/400 on bad/expired tokens).
- **GET** `/auth/register/tenant/validate-invite/?token=<uuid>`

**4. Register via Invite (POST)**

- **POST** `/auth/register/pm/invite/` or `/auth/register/tenant/invite/`
- **Body:** Pass the `invite_token`, along with the rest of the registration fields.

**5. Verify Email**

- **GET** `/auth/verify-email/?token=<uuid>`
- **Behavior:** Returns `200` on success. Frontend should show a "Success, your account is pending admin approval" screen.

---

### B. Login & Logout

**1. Login**

- **POST** `/auth/login/`
- **Body:** `email`, `password`, `remember_me` (optional boolean. If true, refresh token lasts 7 days, else 1 day).
- **Success (200):**

```json
{
  "access": "eyJhbGci...",
  "refresh": "eyJhbGci...",
  "user": {
    "uuid": "...",
    "email": "wanjiru@example.com",
    "role": "landlord",
    "email_verified": true,
    "approval_status": "approved",
    "is_first_login": false,
    "is_demo": false
  }
}
```

- **Failures:**
  - `401 Unauthorized`: "No active account found with the given credentials"
  - `400 Bad Request`: "Please verify your email before logging in." or "Your account is pending admin approval."

**2. Demo Login**

- **POST** `/auth/demo/login/`
- **Body:** None required.
- **Success (200):** Instantly returns tokens for the Demo Landlord.

**3. Logout**

- **POST** `/auth/logout/`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** `{"refresh_token": "<your_refresh_token>"}`
- **Behavior:** This blacklists the refresh token on the server so it can't be used again. (Frontend must also delete tokens from local storage).

---

### C. Password Management

**1. Change Password (Logged in users)**

- **POST** `/auth/change-password/`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** `old_password`, `new_password`, `new_password_confirm`

**2. Password Reset Flow (Forgotten password)**

- **POST** `/auth/password/reset/` (Request link)
  - **Body:** `{"email": "user@example.com"}`
  - **Note:** Always returns `200` to prevent email enumeration hacking.
- **POST** `/auth/password/reset/confirm/` (Submit new password)
  - **Body:** `token`, `new_password`, `new_password_confirm`

---

### D. User Profile & Data

**1. Get Current User**

- **GET** `/auth/me/`
- **Headers:** `Authorization: Bearer <token>`
- **Returns (200):** The authenticated user's profile info.

**2. Update Current User**

- **PATCH** `/auth/me/`
- **Body:** e.g., `{"first_name": "New Name"}`

---

### E. Inviting & Creating Tenants (Landlord & PM Only)

**1. Create Tenant (Instantly generates account and temp password)**

- **POST** `/auth/landlord/create-tenant/` or `/auth/pm/create-tenant/`
- **Body:** `first_name`, `last_name`, `email`, `id_number`, `phone`
- **Returns (201):** `{"message": "...", "tenant_uuid": "..."}`

**2. Invite Tenant (Sends link for them to register)**

- **POST** `/auth/landlord/invite-tenant/` or `/auth/pm/invite-tenant/`
- **Body:** `email`, `name`, `phone`, `unit_number`, `property_name`

---

## 3. Handling Special Frontend States

### 1. `is_first_login`

When a tenant is created by a landlord, `is_first_login` is set to `true`.

- **Frontend Action:** If `user.is_first_login === true` after login, immediately redirect them to a mandatory `/change-password` screen before letting them access the dashboard.

### 2. Demo User Guard

If `user.is_demo === true` is returned from login, you should display a banner: "You are in demo mode. Some features are restricted."

- If the demo user tries to perform a mutating action (POST, PUT, DELETE), the backend will return `403 Forbidden` with:

```json
{
  "error": "demo_restricted",
  "message": "This action is not available in demo mode...",
  "cta": "Create a free account",
  "cta_url": "/register"
}
```

- **Frontend Action:** Catch this specific `error === 'demo_restricted'` globally (in your Axios interceptor) and pop up a nice "Upgrade Account" modal instead of showing a generic error toast.

### 3. Rate Limiting (`429 Too Many Requests`)

DRF throttles requests (e.g. 5 registrations per hour, 10 logins per minute).

- **Frontend Action:** If you receive a `429` status code, show the user: `Too many attempts. Please try again later.`

## Swagger / OpenAPI Docs

For a fully interactive UI to test all exact request/response schemas, run the development server and visit:
`http://localhost:8000/api/docs/`
