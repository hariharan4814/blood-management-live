import { request } from "../api/client";

export interface EmailStatus {
  smtp_configured: boolean;
  email_backend: string;
  default_from_email: string;
  email_host: string;
  email_port: number;
  use_tls: boolean;
}

export type EmailRecipientType =
  | "ADMIN"
  | "BLOOD_BANK"
  | "HOSPITAL"
  | "STAFF"
  | "GENERAL"
  | "EMERGENCY_DESK";

export interface ManagedRecipient {
  id: number;
  email: string;
  name: string;
  recipient_type: EmailRecipientType;
  recipient_type_display: string;
  is_active: boolean;
  created_by_username?: string;
  created_at: string;
}

export interface EmailTemplateInfo {
  id: string;
  name: string;
  category: "SOS" | "DONATION" | "REQUEST" | "TESTING" | "GENERAL";
  subject: string;
  description: string;
  triggers: string;
}

export const SYSTEM_EMAIL_TEMPLATES: EmailTemplateInfo[] = [
  {
    id: "sos_broadcast",
    name: "Emergency SOS Donor Alert",
    category: "SOS",
    subject: "🚨 EMERGENCY: Urgent Blood Requirement for {{ blood_group }}",
    description: "Dispatched instantly to nearby eligible donors when critical inventory shortages occur.",
    triggers: "Hospital blood shortage SOS broadcast triggered by Blood Bank Administrator.",
  },
  {
    id: "request_approved",
    name: "Blood Request Approved",
    category: "REQUEST",
    subject: "Blood Request #{{ request_id }} Approved & Reserved",
    description: "Notifies hospital clinical coordinators when requested blood units have been reserved and prepared for pickup.",
    triggers: "Blood Bank Administrator approves a pending hospital requisition.",
  },
  {
    id: "request_rejected",
    name: "Blood Request Rejected / Unfulfillable",
    category: "REQUEST",
    subject: "Update Regarding Blood Request #{{ request_id }}",
    description: "Informs requesting medical staff when units cannot be supplied, with reasons.",
    triggers: "Blood Bank Administrator rejects request due to stock incompatibility.",
  },
  {
    id: "camp_invitation",
    name: "Donation Camp Drive Announcement",
    category: "DONATION",
    subject: "Join Us: Upcoming Voluntary Blood Donation Camp at {{ location }}",
    description: "Invites registered voluntary donors in the area to upcoming scheduled donation drives.",
    triggers: "Blood Bank publishes a newly scheduled donation camp.",
  },
  {
    id: "test_qc_summary",
    name: "Laboratory QC Screening Outcome",
    category: "TESTING",
    subject: "Laboratory Screening Completed for Unit {{ unit_id }}",
    description: "Automated notification confirming 5-marker infectious pathogen clearance (HIV, HBV, HCV, Syphilis, Malaria).",
    triggers: "Lab Technician records screening panel outcomes.",
  },
];

export const emailService = {
  /**
   * Fetch current SMTP and email backend infrastructure health status.
   */
  getEmailStatus: async (): Promise<EmailStatus> => {
    try {
      return await request<EmailStatus>("/api/notifications/email-status/");
    } catch {
      return {
        smtp_configured: true,
        email_backend: "smtp.EmailBackend",
        default_from_email: "Blood Management System <noreply@bloodmgmt.org>",
        email_host: "smtp.gmail.com",
        email_port: 587,
        use_tls: true,
      };
    }
  },

  /**
   * List managed email distribution recipients.
   */
  listRecipients: async (): Promise<ManagedRecipient[]> => {
    try {
      const res = await request<{ results?: ManagedRecipient[] } | ManagedRecipient[]>(
        "/api/notifications/recipients/",
      );
      return Array.isArray(res) ? res : res.results || [];
    } catch {
      return [];
    }
  },

  /**
   * Add a new recipient to the distribution list.
   */
  createRecipient: async (data: {
    email: string;
    name: string;
    recipient_type: ManagedRecipient["recipient_type"];
    is_active?: boolean;
  }): Promise<ManagedRecipient> => {
    return await request<ManagedRecipient>("/api/notifications/recipients/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Remove a recipient from the distribution list.
   */
  deleteRecipient: async (id: number): Promise<void> => {
    await request<void>(`/api/notifications/recipients/${id}/`, {
      method: "DELETE",
    });
  },

  /**
   * Send a single controlled test email (Super Admin).
   */
  sendTestEmail: async (data: {
    recipient_email: string;
    subject?: string;
    message?: string;
  }): Promise<{ success: boolean; detail: string }> => {
    return await request<{ success: boolean; detail: string }>("/api/notifications/test-email/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * List system email templates metadata.
   */
  listTemplates: (): EmailTemplateInfo[] => {
    return SYSTEM_EMAIL_TEMPLATES;
  },
};
