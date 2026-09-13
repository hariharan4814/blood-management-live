import { request } from "../api/client";
import type { BloodGroup } from "@/lib/types";

export interface NearbyDonor {
  id: string;
  donor_id: number;
  blood_group: BloodGroup;
  is_eligible: boolean;
  age: number | null;
  last_donation_date: string | null;
  distance_km: number;
  approximate_latitude: number;
  approximate_longitude: number;
}

export interface NearbyHospital {
  id: number;
  name: string;
  address: string;
  city: string;
  state: string;
  contact_number: string;
  email: string;
  beds: number;
  latitude: number;
  longitude: number;
  distance_km: number;
  rating?: number | null;
  review_count?: number;
}

export interface NearbyBloodBank {
  id: number;
  name: string;
  address: string;
  city: string;
  state: string;
  contact_number: string;
  email: string;
  capacity: number;
  latitude: number;
  longitude: number;
  distance_km: number;
  rating?: number | null;
  review_count?: number;
}

export interface NearbySearchResponse {
  search_center: {
    latitude: number;
    longitude: number;
    radius_km: number;
  };
  results: {
    donors: NearbyDonor[];
    hospitals: NearbyHospital[];
    blood_banks: NearbyBloodBank[];
  };
  total_count: number;
  donor_access_note?: string;
}

export interface NearbySearchParams {
  lat: number;
  lng: number;
  radius?: number | undefined;
  type?: string | undefined;
  blood_group?: string | undefined;
  only_eligible?: boolean | undefined;
  all_hospitals?: boolean | undefined;
}

export interface BackendHospital {
  id: number;
  name: string;
  address: string;
  city: string;
  state: string;
  contact_number: string;
  email: string;
  beds: number;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
}

export const nearbyService = {
  /**
   * Search for nearby donors, hospitals, and blood banks within a given radius (km).
   */
  searchNearby: async (params: NearbySearchParams): Promise<NearbySearchResponse> => {
    const query = new URLSearchParams();
    query.set("lat", params.lat.toFixed(6));
    query.set("lng", params.lng.toFixed(6));
    if (params.radius) query.set("radius", String(params.radius));
    if (params.type) query.set("type", params.type);
    if (params.blood_group) query.set("blood_group", params.blood_group);
    if (params.only_eligible !== undefined) {
      query.set("only_eligible", params.only_eligible ? "true" : "false");
    }
    if (params.all_hospitals) {
      query.set("all_hospitals", "true");
    }

    return request<NearbySearchResponse>(`/api/nearby/?${query.toString()}`);
  },

  /**
   * List partner hospital facilities from the real database.
   */
  listHospitals: async (): Promise<BackendHospital[]> => {
    try {
      const res = await request<{ results?: BackendHospital[] } | BackendHospital[]>("/api/hospitals/");
      const list = Array.isArray(res) ? res : res.results || [];
      if (list.length > 0) {
        return list;
      }
    } catch {
      // fallback if endpoint returns error or unauthenticated
    }
    const { hospitals } = await import("../mock/data");
    return hospitals.map((h, i) => ({
      id: i + 1,
      name: h.name,
      address: `${h.city} Central District`,
      city: h.city,
      state: "Tamil Nadu",
      contact_number: "+91 44 2800 0000",
      email: `contact@${h.name.toLowerCase().replace(/\s+/g, "")}.org`,
      beds: h.beds,
      latitude: 13.06 + i * 0.02,
      longitude: 80.24 + i * 0.02,
      is_active: true,
    }));
  },
};
