import { request } from "../api/client";
import type { BloodGroup, SosBroadcast, Urgency } from "@/lib/types";

export interface BackendSOSBroadcast {
  id: number;
  blood_request: number;
  blood_request_detail?: {
    id: number;
    hospital_staff_username: string;
    blood_bank_name: string;
    blood_bank_latitude?: number | string | null;
    blood_bank_longitude?: number | string | null;
    blood_bank_address?: string;
    blood_bank_city?: string;
    blood_group: BloodGroup;
    units_needed: number;
    urgency: string;
    status: string;
  };
  triggered_by_username: string;
  status: "ACTIVE" | "COMPLETED" | "CANCELLED";
  status_display: string;
  blood_group: BloodGroup;
  units_needed: number;
  available_units_at_trigger: number;
  shortage_units: number;
  radius_km: number | string | null;
  total_donors_targeted: number;
  title: string;
  message: string;
  created_at: string;
  cancelled_at: string | null;
  cancelled_by_username: string | null;
  cancellation_reason: string | null;
}

export interface BackendSOSRecipient {
  id: number;
  sos_broadcast: number;
  donor: number;
  donor_username: string;
  donor_blood_group: BloodGroup;
  distance_km: number | null;
  notification: number | null;
  email_attempted: boolean;
  email_sent: boolean;
  delivery_error: string;
  created_at: string;
}

export interface CriticalRequestOption {
  id: number;
  blood_group: BloodGroup;
  units_needed: number;
  urgency: string;
  status: string;
  hospital_staff_username: string;
  blood_bank_name: string;
  blood_bank_latitude?: number | string | null;
  blood_bank_longitude?: number | string | null;
  blood_bank_address?: string;
  blood_bank_city?: string;
  blood_bank_state?: string;
}

export interface SOSDonorPreviewItem {
  id: string;
  donor_id: number;
  blood_group: BloodGroup;
  is_eligible: boolean;
  distance_km: number | null;
  approximate_latitude: number | null;
  approximate_longitude: number | null;
}

export interface SOSDonorPreviewResponse {
  blood_request_id: number;
  blood_group_requested: BloodGroup;
  units_needed: number;
  radius_km: number | null;
  center_latitude: number | null;
  center_longitude: number | null;
  eligible_donors_count: number;
  donors: SOSDonorPreviewItem[];
}

export interface SosRecipientItem {
  id: string;
  donorName: string;
  group: BloodGroup;
  distanceKm: number | null;
  phone: string;
  answer: "AVAILABLE" | "PENDING" | "SENT" | "DELIVERED";
}

function mapBroadcast(b: BackendSOSBroadcast): SosBroadcast {
  let status: SosBroadcast["status"] = "ACTIVE";
  if (b.status === "COMPLETED") {
    status = "FULFILLED";
  } else if (b.status === "CANCELLED") {
    status = "EXPIRED";
  }

  return {
    id: `SOS-${b.id}`,
    group: b.blood_group,
    units: b.units_needed,
    hospital:
      b.blood_request_detail?.hospital_staff_username ||
      b.blood_request_detail?.blood_bank_name ||
      "Emergency Dept",
    city: "Metropolis",
    radiusKm: typeof b.radius_km === "number" ? b.radius_km : parseFloat(String(b.radius_km || 25)),
    urgency: "CRITICAL" as Urgency,
    status,
    createdAt: b.created_at,
    notified: b.total_donors_targeted || 0,
    responded: b.total_donors_targeted || 0,
    accepted: b.total_donors_targeted || 0,
  };
}

export const sosService = {
  /**
   * List all Emergency SOS broadcasts.
   */
  listBroadcasts: async (): Promise<SosBroadcast[]> => {
    try {
      const res = await request<
        { results?: BackendSOSBroadcast[] } | BackendSOSBroadcast[]
      >("/api/sos/");
      const list = Array.isArray(res) ? res : res.results || [];
      return list.map(mapBroadcast);
    } catch {
      return [];
    }
  },

  /**
   * List donor recipients targeted by a specific broadcast.
   */
  listResponses: async (broadcastId: string | number): Promise<SosRecipientItem[]> => {
    const rawId = typeof broadcastId === "string" ? broadcastId.replace(/^SOS-/, "") : broadcastId;
    try {
      const res = await request<
        { results?: BackendSOSRecipient[] } | BackendSOSRecipient[]
      >(`/api/sos/${rawId}/recipients/`);
      const list = Array.isArray(res) ? res : res.results || [];

      return list.map((r) => ({
        id: String(r.id),
        donorName: r.donor_username || `Eligible Donor #${r.donor}`,
        group: r.donor_blood_group,
        distanceKm: typeof r.distance_km === "number" ? r.distance_km : null,
        phone: "Contact via Email Notification",
        answer: r.email_sent ? "DELIVERED" : "SENT",
      }));
    } catch {
      return [];
    }
  },

  /**
   * Fetch eligible critical blood requests available for triggering an SOS broadcast.
   */
  listCriticalRequests: async (): Promise<CriticalRequestOption[]> => {
    try {
      const res = await request<
        { results?: CriticalRequestOption[] } | CriticalRequestOption[]
      >("/api/blood-requests/?urgency=CRITICAL&status=PENDING");
      return Array.isArray(res) ? res : res.results || [];
    } catch {
      return [];
    }
  },

  /**
   * Trigger an Emergency SOS broadcast for an eligible critical blood request.
   */
  triggerForRequest: async (
    requestId: number,
    radiusKm: number,
  ): Promise<SosBroadcast> => {
    const res = await request<BackendSOSBroadcast>(`/api/blood-requests/${requestId}/sos/`, {
      method: "POST",
      body: JSON.stringify({ radius_km: radiusKm }),
    });
    return mapBroadcast(res);
  },

  /**
   * Cancel an active SOS broadcast.
   */
  cancelBroadcast: async (broadcastId: string | number, reason: string): Promise<void> => {
    const rawId = typeof broadcastId === "string" ? broadcastId.replace(/^SOS-/, "") : broadcastId;
    await request(`/api/sos/${rawId}/cancel/`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },

  /**
   * Preview eligible, compatible donors for a critical blood request within a geographic radius.
   * Read-only preview: does not trigger broadcast, does not send notifications.
   */
  getDonorPreview: async (
    requestId: number,
    radiusKm: number,
  ): Promise<SOSDonorPreviewResponse> => {
    return await request<SOSDonorPreviewResponse>(
      `/api/blood-requests/${requestId}/sos/preview/?radius_km=${radiusKm}`,
    );
  },

  /**
   * Alias helper for donor SOS alert component.
   */
  respond: async (broadcastId: string, answer: "AVAILABLE" | "UNAVAILABLE") => {
    return { broadcastId, answer };
  },
};
