import { request } from "../api/client";
import type { BloodGroup, BloodUnitStatus, TestRecord, TestResult } from "@/lib/types";

export interface BackendBloodUnit {
  id: number;
  unit_id: string;
  blood_bank: number;
  blood_bank_name: string;
  blood_group: BloodGroup;
  collection_date: string;
  expiry_date: string;
  status: BloodUnitStatus;
  created_at: string;
}

export interface BackendTestResult {
  id: number;
  blood_unit: number;
  blood_unit_id: number;
  unit_id: string;
  blood_group: BloodGroup;
  blood_unit_status: string;
  blood_bank_id: number;
  blood_bank_name: string;
  hiv_result: "PENDING" | "NEGATIVE" | "POSITIVE";
  hepatitis_b_result: "PENDING" | "NEGATIVE" | "POSITIVE";
  hepatitis_c_result: "PENDING" | "NEGATIVE" | "POSITIVE";
  syphilis_result: "PENDING" | "NEGATIVE" | "POSITIVE";
  malaria_result: "PENDING" | "NEGATIVE" | "POSITIVE";
  overall_outcome: string;
  tested_by_id: number | null;
  tested_by_username: string | null;
  tested_at: string | null;
  created_at: string;
  updated_at: string;
}

export const TEST_TYPES = ["HIV", "Hepatitis B", "Hepatitis C", "Syphilis", "Malaria"];

function mapOutcome(backendOutcome?: string, unitStatus?: string): TestResult {
  if (backendOutcome === "PASSED" || unitStatus === "AVAILABLE") return "PASS";
  if (backendOutcome === "FAILED" || unitStatus === "DISCARDED") return "FAIL";
  return "PENDING";
}

function mapScreening(result: string): TestResult {
  if (result === "NEGATIVE") return "PASS";
  if (result === "POSITIVE") return "FAIL";
  return "PASS";
}

export const testingService = {
  testTypes: TEST_TYPES,

  /**
   * List all blood units currently queued in TESTING status awaiting laboratory clearance.
   */
  listPending: async (): Promise<TestRecord[]> => {
    try {
      const res = await request<
        { results?: BackendBloodUnit[] } | BackendBloodUnit[]
      >("/api/blood-units/?status=TESTING");
      const list = Array.isArray(res) ? res : res.results || [];
      return list.map((u) => ({
        id: String(u.id),
        unitId: u.unit_id,
        group: u.blood_group,
        collectedAt: u.collection_date || u.created_at,
        results: {},
        outcome: "PENDING" as TestResult,
      }));
    } catch {
      return [];
    }
  },

  /**
   * List historical screening test results with per-marker outcomes.
   */
  listHistory: async (): Promise<TestRecord[]> => {
    try {
      const res = await request<
        { results?: BackendTestResult[] } | BackendTestResult[]
      >("/api/test-results/");
      const list = Array.isArray(res) ? res : res.results || [];
      return list.map((r) => ({
        id: String(r.id),
        unitId: r.unit_id || `UNIT-${r.blood_unit}`,
        group: r.blood_group,
        collectedAt: r.created_at,
        technician: r.tested_by_username || "Lab Technician",
        testedAt: r.tested_at || r.updated_at || r.created_at,
        results: {
          HIV: mapScreening(r.hiv_result),
          "Hepatitis B": mapScreening(r.hepatitis_b_result),
          "Hepatitis C": mapScreening(r.hepatitis_c_result),
          Syphilis: mapScreening(r.syphilis_result),
          Malaria: mapScreening(r.malaria_result),
        },
        outcome: mapOutcome(r.overall_outcome, r.blood_unit_status),
      }));
    } catch {
      return [];
    }
  },

  /**
   * Record laboratory screening outcomes for a blood unit.
   * Atomically updates BloodUnit status to AVAILABLE or DISCARDED.
   */
  submitResult: async (
    unitId: string | number,
    results: Record<string, TestResult>,
  ): Promise<{ outcome: "PASS" | "FAIL" }> => {
    const rawUnitId = typeof unitId === "string" ? parseInt(unitId, 10) : unitId;

    const payload = {
      blood_unit: rawUnitId,
      hiv_result: results["HIV"] === "FAIL" ? "POSITIVE" : "NEGATIVE",
      hepatitis_b_result: results["Hepatitis B"] === "FAIL" ? "POSITIVE" : "NEGATIVE",
      hepatitis_c_result: results["Hepatitis C"] === "FAIL" ? "POSITIVE" : "NEGATIVE",
      syphilis_result: results["Syphilis"] === "FAIL" ? "POSITIVE" : "NEGATIVE",
      malaria_result: results["Malaria"] === "FAIL" ? "POSITIVE" : "NEGATIVE",
    };

    const res = await request<BackendTestResult>("/api/test-results/", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    const isPass = res.overall_outcome === "PASSED" || res.blood_unit_status === "AVAILABLE";
    return { outcome: isPass ? "PASS" : "FAIL" };
  },
};
