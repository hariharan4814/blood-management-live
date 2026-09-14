import { mockRequest, request } from "../api/client";
import { setTokens, clearTokens } from "@/lib/tokens";
import { ROLE_LABELS, type Role } from "@/lib/types";

export interface AuthUser {
  id: number | string;
  username: string;
  email: string;
  role: Role;
  phone?: string | null;
  address?: string | null;
  is_verified?: boolean;
  first_name?: string;
  last_name?: string;
  name: string;
  organization: string;
}

export interface LoginPayload {
  email?: string;
  username?: string;
  password: string;
  role?: Role;
  remember?: boolean;
}

export interface RegisterPayload {
  username?: string;
  name?: string;
  email: string;
  phone?: string;
  password: string;
  password_confirm?: string;
  role: Extract<Role, "DONOR" | "HOSPITAL_STAFF">;
  blood_group?: string;
  city?: string;
  state?: string;
  address?: string;
  hospital_name?: string;
  hospital?: string;
  contact_person_name?: string;
  latitude?: number | null;
  longitude?: number | null;
  staffId?: string;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: AuthUser;
}

export interface RegisterResponse {
  message: string;
  user: AuthUser;
}

function formatUser(rawUser: Record<string, unknown>): AuthUser {
  const role = (rawUser["role"] as Role) || "DONOR";
  const firstName = String(rawUser["first_name"] || "").trim();
  const lastName = String(rawUser["last_name"] || "").trim();
  const username = String(rawUser["username"] || "");
  const email = String(rawUser["email"] || "");
  const address = String(rawUser["address"] || "").trim();

  const name =
    firstName || lastName
      ? `${firstName} ${lastName}`.trim()
      : username || (email.split("@")[0] ? email.split("@")[0] : "") || ROLE_LABELS[role];

  let organization = "Blood Management System";
  if (role === "DONOR") {
    organization = "Individual Donor";
  } else if (role === "HOSPITAL_STAFF") {
    const hospName = String(rawUser["hospital_name"] || "");
    organization = hospName ? `${hospName}` : (address || "Hospital Staff Member");
  } else if (role === "BLOOD_BANK_ADMIN") {
    organization = "Blood Bank Facility";
  } else if (role === "LAB_TECHNICIAN") {
    organization = "Testing & Quality Laboratory";
  } else if (role === "SUPER_ADMIN") {
    organization = "Platform Administration";
  } else if (address) {
    organization = address;
  }

  return {
    id: (rawUser["id"] as number | string) || username,
    username,
    email,
    role,
    phone: (rawUser["phone"] as string) || null,
    address: address || null,
    is_verified: Boolean(rawUser["is_verified"]),
    first_name: firstName,
    last_name: lastName,
    name,
    organization,
  };
}

export const authService = {
  /**
   * Real Django JWT Login (POST /api/auth/login/).
   * Accepts username or email.
   */
  login: async ({ email, username, password }: LoginPayload): Promise<LoginResponse> => {
    const loginIdentifier = (username || email || "").trim();

    const response = await request<{ access: string; refresh: string; user: Record<string, unknown> }>(
      "/api/auth/login/",
      {
        method: "POST",
        body: JSON.stringify({
          username: loginIdentifier,
          password,
        }),
      },
    );

    setTokens(response.access, response.refresh);
    const user = formatUser(response.user || {});

    return {
      access: response.access,
      refresh: response.refresh,
      user,
    };
  },

  /**
   * Real Django Registration (POST /api/auth/register/).
   * Permitted for DONOR and HOSPITAL_STAFF roles.
   */
  register: async (payload: RegisterPayload): Promise<RegisterResponse> => {
    let generatedUsername = payload.username?.trim();
    if (!generatedUsername) {
      const emailParts = payload.email.split("@");
      const emailPrefix = (emailParts[0] || "").replace(/[^a-zA-Z0-9_]/g, "_").toLowerCase();
      generatedUsername = emailPrefix || `user_${Date.now()}`;
    }

    const body: Record<string, unknown> = {
      username: generatedUsername,
      name: payload.name?.trim() || "",
      email: payload.email.trim().toLowerCase(),
      password: payload.password,
      password_confirm: payload.password_confirm || payload.password,
      role: payload.role,
      phone: payload.phone?.trim() || "",
      address: payload.hospital?.trim() || payload.city?.trim() || "",
      hospital: payload.hospital?.trim() || "",
      ...(payload.blood_group ? { blood_group: payload.blood_group } : {}),
      ...(payload.contact_person_name ? { contact_person_name: payload.contact_person_name } : {}),
      ...(payload.name ? { contact_person_name: payload.name } : {}),
      ...(payload.hospital_name ? { hospital_name: payload.hospital_name } : {}),
      ...(payload.hospital ? { hospital: payload.hospital } : {}),
      ...(payload.city ? { city: payload.city } : {}),
      ...(payload.state ? { state: payload.state } : {}),
      ...(payload.address ? { address: payload.address } : {}),
      ...(typeof payload.latitude === "number" ? { latitude: payload.latitude } : {}),
      ...(typeof payload.longitude === "number" ? { longitude: payload.longitude } : {}),
    };

    const response = await request<{ message: string; user: Record<string, unknown> }>("/api/auth/register/", {
      method: "POST",
      body: JSON.stringify(body),
    });

    return {
      message: response.message,
      user: formatUser(response.user || {}),
    };
  },

  /**
   * Real Django Current User Profile (GET /api/auth/me/).
   */
  getCurrentUser: async (): Promise<AuthUser> => {
    const raw = await request<Record<string, unknown>>("/api/auth/me/");
    return formatUser(raw);
  },

  /**
   * Refresh JWT Access Token (POST /api/auth/token/refresh/).
   */
  refreshToken: async (refresh: string): Promise<{ access: string }> => {
    return request<{ access: string }>("/api/auth/token/refresh/", {
      method: "POST",
      body: JSON.stringify({ refresh }),
    });
  },

  /**
   * Helper methods for unintegrated password reset pages.
   */
  requestPasswordReset: (email: string) => mockRequest({ ok: true, email }),
  resetPassword: (token: string) => mockRequest({ ok: true, token }),

  /**
   * Logout helper.
   */
  logout: () => {
    clearTokens();
  },
};
