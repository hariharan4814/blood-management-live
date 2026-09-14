import { request } from "../api/client";
import { BLOOD_GROUPS, type BloodGroup, type BloodUnitStatus } from "@/lib/types";

export interface BackendInventoryItem {
  blood_group: BloodGroup;
  available_units: number;
}

export interface BackendBankSummary {
  blood_bank: {
    id: number;
    name: string;
    city: string;
    state: string;
  };
  inventory: BackendInventoryItem[];
  total_available_units: number;
}

export interface BackendBloodUnit {
  id: number;
  blood_bank: number;
  blood_bank_name: string;
  unit_id: string;
  blood_group: BloodGroup;
  collection_date: string;
  expiry_date: string;
  status: BloodUnitStatus;
  status_display: string;
  is_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface BloodStock {
  group: BloodGroup;
  units: number;
  reserved: number;
  testing: number;
  threshold: number;
}

export interface BloodUnitItem {
  id: string;
  rawId: number;
  group: BloodGroup;
  donorName: string;
  collectedAt: string;
  expiresAt: string;
  volumeMl: number;
  status: BloodUnitStatus;
  bank: string;
  isExpired: boolean;
}

const DEFAULT_THRESHOLD = 5;

export interface BloodUnitCreateInput {
  blood_bank: number;
  blood_group: BloodGroup;
  collection_date: string;
  unit_id?: string | undefined;
}

export const inventoryService = {
  /**
   * Register a new blood unit in the inventory (initial status forced to TESTING).
   */
  createUnit: async (data: BloodUnitCreateInput): Promise<BackendBloodUnit> => {
    return await request<BackendBloodUnit>("/api/blood-units/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Fetch aggregate stock breakdown across all blood groups.
   */
  getStock: async (): Promise<BloodStock[]> => {
    try {
      const response = await request<BackendBankSummary[] | BackendBankSummary>("/api/inventory/summary/");
      const summaries = Array.isArray(response) ? response : [response];

      // Initialize map for all supported blood groups
      const groupStockMap = BLOOD_GROUPS.reduce((acc, bg) => {
        acc[bg] = 0;
        return acc;
      }, {} as Record<BloodGroup, number>);

      for (const summary of summaries) {
        if (summary && Array.isArray(summary.inventory)) {
          for (const item of summary.inventory) {
            if (item.blood_group in groupStockMap) {
              groupStockMap[item.blood_group] += item.available_units || 0;
            }
          }
        }
      }

      return BLOOD_GROUPS.map((group) => ({
        group,
        units: groupStockMap[group] || 0,
        reserved: 0,
        testing: 0,
        threshold: DEFAULT_THRESHOLD,
      }));
    } catch {
      // Fallback empty baseline for all 8 groups if inventory empty
      return BLOOD_GROUPS.map((group) => ({
        group,
        units: 0,
        reserved: 0,
        testing: 0,
        threshold: DEFAULT_THRESHOLD,
      }));
    }
  },

  /**
   * List individual blood units with optional filtering.
   */
  listUnits: async (params?: {
    group?: string;
    status?: string;
    blood_bank?: number;
  }): Promise<BloodUnitItem[]> => {
    const query = new URLSearchParams();
    if (params?.group && params.group !== "ALL") query.set("blood_group", params.group);
    if (params?.status && params.status !== "ALL") query.set("status", params.status);
    if (params?.blood_bank) query.set("blood_bank", String(params.blood_bank));

    const queryString = query.toString() ? `?${query.toString()}` : "";
    const response = await request<{ count?: number; results?: BackendBloodUnit[] } | BackendBloodUnit[]>(
      `/api/blood-units/${queryString}`,
    );

    const rawUnits = Array.isArray(response) ? response : response.results || [];

    return rawUnits.map((u) => ({
      id: u.unit_id || `BU-${u.id}`,
      rawId: u.id,
      group: u.blood_group,
      donorName: "Registered Donor",
      collectedAt: u.collection_date,
      expiresAt: u.expiry_date,
      volumeMl: 450,
      status: u.status,
      bank: u.blood_bank_name || "Blood Bank Facility",
      isExpired: Boolean(u.is_expired),
    }));
  },

  /**
   * Filter stock groups that fall below the safety threshold.
   */
  getLowStock: async (): Promise<BloodStock[]> => {
    const stock = await inventoryService.getStock();
    return stock.filter((s) => s.units < s.threshold);
  },
};
