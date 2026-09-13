import { request } from "../api/client";
import type { BloodGroup, RequestStatus, Urgency, BloodRequest } from "@/lib/types";

export interface BackendBloodRequest {
  id: number;
  hospital_staff: number;
  hospital_staff_username: string;
  blood_bank: number;
  blood_bank_name: string;
  blood_group: BloodGroup;
  units_needed: number;
  urgency: Urgency;
  urgency_display: string;
  status: RequestStatus;
  status_display: string;
  rejection_reason: string;
  approved_by: number | null;
  approved_by_username: string | null;
  approved_at: string | null;
  reserved_units_count: number;
  created_at: string;
  updated_at: string;
}

export interface BloodBankOption {
  id: number;
  name: string;
  city: string;
  state: string;
  contact_number: string;
}

function mapBackendRequest(r: BackendBloodRequest): BloodRequest {
  const timeline: BloodRequest["timeline"] = [
    {
      status: "CREATED",
      at: r.created_at,
      by: r.hospital_staff_username || "Hospital Staff",
      note: "Request raised and submitted for facility review.",
    },
  ];

  if (r.status === "APPROVED" || r.approved_at) {
    timeline.push({
      status: "APPROVED",
      at: r.approved_at || r.updated_at,
      by: r.approved_by_username || "Blood Bank Admin",
      note: `${r.reserved_units_count || r.units_needed} unit(s) allocated and reserved in inventory.`,
    });
  } else if (r.status === "REJECTED") {
    timeline.push({
      status: "REJECTED",
      at: r.updated_at,
      by: "Blood Bank Admin",
      note: r.rejection_reason ? `Reason: ${r.rejection_reason}` : "Request could not be fulfilled.",
    });
  } else if (r.status === "DISPATCHED") {
    timeline.push({
      status: "DISPATCHED",
      at: r.updated_at,
      by: "Logistics Team",
      note: "Blood units dispatched for delivery to medical facility.",
    });
  } else if (r.status === "COMPLETED") {
    timeline.push({
      status: "COMPLETED",
      at: r.updated_at,
      by: "Receiving Staff",
      note: "Units received and verified by hospital staff.",
    });
  }

  const result: BloodRequest = {
    id: `REQ-${r.id}`,
    hospital: r.blood_bank_name ? `${r.hospital_staff_username} → ${r.blood_bank_name}` : r.hospital_staff_username || "Hospital Facility",
    patientRef: `PT-2026-${String(r.id).padStart(4, "0")}`,
    group: r.blood_group,
    units: r.units_needed,
    urgency: r.urgency,
    status: r.status,
    requestedBy: r.hospital_staff_username || "Hospital Staff",
    createdAt: r.created_at,
    neededBy: r.created_at,
    timeline,
  };

  if (r.rejection_reason) {
    result.notes = r.rejection_reason;
  }

  return result;
}

export const requestService = {
  /**
   * List all blood requests with optional status/urgency filtering.
   */
  list: async (params?: { status?: string; urgency?: string; blood_group?: string }): Promise<BloodRequest[]> => {
    const query = new URLSearchParams();
    if (params?.status && params.status !== "ALL") query.set("status", params.status);
    if (params?.urgency && params.urgency !== "ALL") query.set("urgency", params.urgency);
    if (params?.blood_group && params.blood_group !== "ALL") query.set("blood_group", params.blood_group);

    const queryString = query.toString() ? `?${query.toString()}` : "";
    const response = await request<{ count?: number; results?: BackendBloodRequest[] } | BackendBloodRequest[]>(
      `/api/blood-requests/${queryString}`,
    );

    const rawList = Array.isArray(response) ? response : response.results || [];
    return rawList.map(mapBackendRequest);
  },

  /**
   * Retrieve single blood request details.
   */
  get: async (id: string | number): Promise<BloodRequest | null> => {
    const rawId = typeof id === "string" ? id.replace(/^REQ-/, "") : id;
    try {
      const res = await request<BackendBloodRequest>(`/api/blood-requests/${rawId}/`);
      return mapBackendRequest(res);
    } catch {
      return null;
    }
  },

  /**
   * Raise a new blood request (Hospital Staff only).
   */
  create: async (payload: {
    blood_bank: number;
    blood_group: BloodGroup;
    units_needed: number;
    urgency: Urgency;
  }): Promise<BloodRequest> => {
    const res = await request<BackendBloodRequest>("/api/blood-requests/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return mapBackendRequest(res);
  },

  /**
   * Approve a pending blood request and reserve units (Blood Bank Admin only).
   */
  approve: async (id: string | number): Promise<BloodRequest> => {
    const rawId = typeof id === "string" ? id.replace(/^REQ-/, "") : id;
    const res = await request<BackendBloodRequest>(`/api/blood-requests/${rawId}/approve/`, {
      method: "POST",
    });
    return mapBackendRequest(res);
  },

  /**
   * Reject a pending blood request with explanation reason (Blood Bank Admin only).
   */
  reject: async (id: string | number, reason: string): Promise<BloodRequest> => {
    const rawId = typeof id === "string" ? id.replace(/^REQ-/, "") : id;
    const res = await request<BackendBloodRequest>(`/api/blood-requests/${rawId}/reject/`, {
      method: "POST",
      body: JSON.stringify({ rejection_reason: reason.trim() }),
    });
    return mapBackendRequest(res);
  },

  /**
   * Fetch active blood banks for target selection in request form.
   */
  listBloodBanks: async (): Promise<BloodBankOption[]> => {
    const res = await request<{ results?: BloodBankOption[] } | BloodBankOption[]>("/api/blood-banks/");
    return Array.isArray(res) ? res : res.results || [];
  },
};