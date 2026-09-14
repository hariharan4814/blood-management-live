import { request } from "../api/client";
import type { Role } from "@/lib/types";

export interface DonorContactRequestItem {
  id: number;
  requester_id: number;
  requester_username: string;
  requester_name: string;
  requester_role: Role;
  donor_id: number;
  donor_blood_group?: string;
  hospital_name?: string;
  blood_group?: string;
  urgency?: string;
  message?: string;
  reason?: string;
  status: "PENDING" | "APPROVED" | "DECLINED";
  responded_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DonorPrivateContact {
  id: number;
  user_id: number;
  username: string;
  full_name: string;
  email: string;
  phone: string;
  address: string;
  blood_group: string;
  latitude?: number | null;
  longitude?: number | null;
  is_eligible: boolean;
}

export const donorContactService = {
  /**
   * Submit an explicit request for access to donor contact details.
   */
  createContactRequest: async (donorId: number, reason: string): Promise<DonorContactRequestItem> => {
    return request<DonorContactRequestItem>("/api/donors/contact-requests/", {
      method: "POST",
      body: JSON.stringify({
        donor_id: donorId,
        reason,
      }),
    });
  },

  /**
   * List contact requests (sent or received).
   */
  getContactRequests: async (params?: { view_as?: "requester" | "donor"; status?: string }): Promise<DonorContactRequestItem[]> => {
    const query = new URLSearchParams();
    if (params?.view_as) query.append("view_as", params.view_as);
    if (params?.status) query.append("status", params.status);
    const qs = query.toString() ? `?${query.toString()}` : "";
    return request<DonorContactRequestItem[]>(`/api/donors/contact-requests/${qs}`);
  },

  /**
   * Donor responds to a contact request (APPROVED or DECLINED / APPROVE or DECLINE).
   */
  respondToContactRequest: async (
    requestId: number,
    status: "APPROVED" | "DECLINED" | "APPROVE" | "DECLINE",
  ): Promise<DonorContactRequestItem> => {
    return request<DonorContactRequestItem>(`/api/donors/contact-requests/${requestId}/respond/`, {
      method: "POST",
      body: JSON.stringify({ action: status, status }),
    });
  },

  /**
   * Disclose private contact details if caller has an APPROVED contact request.
   */
  getDonorContactDetails: async (donorId: number): Promise<DonorPrivateContact> => {
    return request<DonorPrivateContact>(`/api/donors/${donorId}/contact-details/`);
  },
};
