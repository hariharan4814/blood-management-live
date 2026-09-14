import { request } from "../api/client";
import { profileService } from "../profile/profileService";
import type { BloodGroup, DonationRecord, User } from "@/lib/types";

export type { DonationRecord };

export interface BackendDonation {
  id: number;
  donor: number;
  donor_name: string;
  blood_bank: number;
  blood_bank_name: string;
  camp: number | null;
  camp_name: string | null;
  donation_date: string;
  units_donated: number;
  donor_blood_group: BloodGroup;
  status: string;
  notes: string;
  created_at: string;
}

export interface BackendDonorProfile {
  id: number;
  user_id: number;
  username: string;
  email: string;
  phone: string;
  blood_group: BloodGroup;
  date_of_birth: string;
  age: number;
  weight_kg: string | number;
  latitude: string | number;
  longitude: string | number;
  last_donation_date: string | null;
  is_eligible: boolean;
  created_at: string;
  updated_at: string;
}

export const donorService = {
  /**
   * Fetch full donor profile combining personal metadata and donor attributes.
   */
  getProfile: async () => {
    const [p, d, elig, donations] = await Promise.all([
      profileService.getProfile(),
      profileService.getDonorDetails(),
      profileService.getDonorEligibility(),
      request<{ count?: number; results?: BackendDonation[] } | BackendDonation[]>("/api/donations/"),
    ]);
    return {
      id: d ? `DONOR-${d.id}` : `USR-${p.id}`,
      name: p.full_name || p.username || "Registered Donor",
      email: p.email || "",
      phone: p.phone || "",
      dob: d?.date_of_birth || null,
      weightKg: d?.weight_kg ?? null,
      address: p.address || "",
      group: d?.blood_group || "Unknown",
      totalDonations: Array.isArray(donations) ? donations.length : donations.count ?? null,
      lastDonation: d?.last_donation_date || null,
      nextEligible: elig ? (elig.is_eligible ? "Eligible now" : "See eligibility checklist") : "Complete your donor profile",
      eligible: elig?.is_eligible ?? false,
    };
  },

  /** Eligibility comes exclusively from the canonical backend service. */
  checkEligibility: async () => {
    const elig = await profileService.getDonorEligibility();
    if (!elig) throw new Error("Complete your donor profile to check eligibility.");
    return {
      eligible: elig.is_eligible,
      reasons: [
        { label: "Minimum 90 days since last donation", passed: elig.criteria.donation_interval.passed },
        { label: "Weight at least 50 kg", passed: elig.criteria.weight.passed },
        { label: "Age between 18 and 65 years", passed: elig.criteria.age.passed },
      ],
    };
  },

  /**
   * Fetch donation history for authenticated donor.
   */
  getDonationHistory: async (): Promise<DonationRecord[]> => {
    try {
      const res = await request<{ results?: BackendDonation[] } | BackendDonation[]>(
        "/api/donations/",
      );
      const list = Array.isArray(res) ? res : res.results || [];
      return list.map((d) => ({
        id: `DON-${d.id}`,
        date: d.donation_date || d.created_at,
        center: d.camp_name || d.blood_bank_name || "Blood Bank Facility",
        group: d.donor_blood_group,
        volumeMl: null,
        status: "COMPLETED" as DonationRecord["status"],
      }));
    } catch {
      return [];
    }
  },

  /**
   * List all registered donors (Staff / Admin).
   */
  listDonors: async (): Promise<User[]> => {
    try {
      const res = await request<
        { results?: BackendDonorProfile[] } | BackendDonorProfile[]
      >("/api/donors/");
      const list = Array.isArray(res) ? res : res.results || [];
      if (list.length > 0) {
        return list.map((d) => ({
          id: `DONOR-${d.id}`,
          name: d.username ? d.username.charAt(0).toUpperCase() + d.username.slice(1) : "Registered Donor",
          email: d.email || "",
          role: "DONOR" as const,
          organization: d.blood_group ? `Blood Group ${d.blood_group}` : "Blood group unknown",
          status: "ACTIVE" as const,
          joinedAt: d.created_at || "",
        }));
      }
    } catch {
      // fallback
    }

    try {
      const res = await request<{ results?: any[] } | any[]>("/api/users/?role=DONOR");
      const list = Array.isArray(res) ? res : res.results || [];
      if (list.length > 0) {
        return list.map((u) => {
          const fullName = [u.first_name, u.last_name].filter(Boolean).join(" ").trim();
          return {
            id: `USR-${u.id}`,
            name: fullName || u.username || "Registered Donor",
            email: u.email || "",
            role: "DONOR" as const,
            organization: "Voluntary Donor",
            status: u.is_active === false ? ("SUSPENDED" as const) : ("ACTIVE" as const),
            joinedAt: u.date_joined || "",
          };
        });
      }
    } catch {
      // fallback
    }

    return [];
  },

  /**
   * Request privacy-preserving contact access for a specific donor.
   */
  requestContactAccess: async (data: {
    donor_id: number;
    hospital_name?: string;
    blood_group?: string;
    urgency?: string;
    message?: string;
  }): Promise<DonorContactRequestItem> => {
    return request<DonorContactRequestItem>("/api/donors/contact-requests/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * List contact requests (incoming for donors, sent for hospital/staff/admins).
   */
  listContactRequests: async (): Promise<DonorContactRequestItem[]> => {
    try {
      const res = await request<DonorContactRequestItem[] | { results: DonorContactRequestItem[] }>(
        "/api/donors/contact-requests/",
      );
      return Array.isArray(res) ? res : res.results || [];
    } catch {
      return [];
    }
  },

  /**
   * Retrieve a specific contact request.
   */
  getContactRequest: async (id: number): Promise<DonorContactRequestItem> => {
    return request<DonorContactRequestItem>(`/api/donors/contact-requests/${id}/`);
  },

  /**
   * Donor decision to accept or decline a contact request.
   */
  respondToContactRequest: async (
    id: number,
    action: "APPROVE" | "DECLINE",
    notes?: string,
  ): Promise<DonorContactRequestItem> => {
    return request<DonorContactRequestItem>(`/api/donors/contact-requests/${id}/respond/`, {
      method: "POST",
      body: JSON.stringify({ action, notes }),
    });
  },
};

export interface DonorContactRequestItem {
  id: number;
  blood_request?: number | null;
  blood_request_id?: number | null;
  donor_id: number;
  donor_display: string;
  donor_blood_group?: string;
  requester_id: number;
  requester_name: string;
  hospital_name: string;
  blood_group: string;
  urgency: string;
  message: string;
  status: "PENDING" | "APPROVED" | "DECLINED";
  responded_at: string | null;
  donation?: number | null;
  donation_id?: number | null;
  donation_outcome?: "NOT_RECORDED" | "COMPLETED" | "DID_NOT_HAPPEN";
  donation_outcome_display?: string;
  outcome_recorded_at?: string | null;
  outcome_recorded_by?: number | null;
  outcome_recorded_by_name?: string | null;
  outcome_notes?: string;
  created_at: string;
  updated_at: string;
  contact_details?: {
    name: string;
    phone: string;
    email: string;
    blood_group: string;
  } | null;
}
