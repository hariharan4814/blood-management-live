export type Role =
  | "SUPER_ADMIN"
  | "BLOOD_BANK_ADMIN"
  | "HOSPITAL_STAFF"
  | "LAB_TECHNICIAN"
  | "DONOR";

export const ROLE_LABELS: Record<Role, string> = {
  SUPER_ADMIN: "Super Admin",
  BLOOD_BANK_ADMIN: "Blood Bank Admin",
  HOSPITAL_STAFF: "Hospital Staff",
  LAB_TECHNICIAN: "Lab Technician",
  DONOR: "Donor",
};

export type BloodGroup =
  | "O+"
  | "O-"
  | "A+"
  | "A-"
  | "B+"
  | "B-"
  | "AB+"
  | "AB-"
  | "A1+"
  | "A1-"
  | "A2+"
  | "A2-"
  | "A1B+"
  | "A1B-"
  | "A2B+"
  | "A2B-";

export const BLOOD_GROUPS: BloodGroup[] = [
  "O+",
  "O-",
  "A+",
  "A-",
  "B+",
  "B-",
  "AB+",
  "AB-",
  "A1+",
  "A1-",
  "A2+",
  "A2-",
  "A1B+",
  "A1B-",
  "A2B+",
  "A2B-",
];

export type UnitStatus = "TESTING" | "AVAILABLE" | "RESERVED" | "DISPATCHED" | "DISCARDED";
export type BloodUnitStatus = UnitStatus;
export type RequestStatus = "PENDING" | "APPROVED" | "REJECTED" | "DISPATCHED" | "COMPLETED";
export type Urgency = "NORMAL" | "HIGH" | "CRITICAL";
export type TestResult = "PASS" | "FAIL" | "PENDING";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  organization: string;
  status: "ACTIVE" | "SUSPENDED";
  joinedAt: string;
}

export interface BloodStock {
  group: BloodGroup;
  units: number;
  reserved: number;
  testing: number;
  threshold: number;
}

export interface BloodUnit {
  id: string;
  group: BloodGroup;
  donorName: string;
  collectedAt: string;
  expiresAt: string;
  volumeMl: number;
  status: UnitStatus;
  bank: string;
}

export interface TestRecord {
  id: string;
  unitId: string;
  group: BloodGroup;
  collectedAt: string;
  technician?: string;
  testedAt?: string;
  results: Record<string, TestResult>;
  outcome: TestResult;
  notes?: string;
}

export interface BloodRequest {
  id: string;
  hospital: string;
  patientRef: string;
  group: BloodGroup;
  units: number;
  urgency: Urgency;
  status: RequestStatus;
  requestedBy: string;
  createdAt: string;
  neededBy: string;
  notes?: string;
  timeline: { status: RequestStatus | "CREATED"; at: string; by: string; note?: string }[];
}

export interface Camp {
  id: string;
  name: string;
  organizer: string;
  city: string;
  address: string;
  date: string;
  startTime: string;
  endTime: string;
  slots: number;
  registered: number;
  status: "UPCOMING" | "ONGOING" | "COMPLETED";
  description: string;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  category: "EMERGENCY" | "REQUEST" | "INVENTORY" | "CAMP" | "SYSTEM";
  createdAt: string;
  read: boolean;
}

export interface DonationRecord {
  id: string;
  date: string;
  center: string;
  group: BloodGroup;
  volumeMl: number | null;
  status: "COMPLETED" | "DEFERRED";
}

export interface SosBroadcast {
  id: string;
  group: BloodGroup;
  units: number;
  hospital: string;
  city: string;
  radiusKm: number;
  urgency: Urgency;
  status: "ACTIVE" | "FULFILLED" | "EXPIRED";
  createdAt: string;
  notified: number;
  responded: number;
  accepted: number;
}

export interface SosResponse {
  id: string;
  donorName: string;
  group: BloodGroup;
  distanceKm: number;
  respondedAt: string;
  answer: "AVAILABLE" | "UNAVAILABLE" | "NO_RESPONSE";
  phone: string;
}
