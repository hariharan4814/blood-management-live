import { useState, useEffect } from "react";
import { CheckCircle2, Clock, Lock, Mail, Phone, MapPin, Send, ShieldAlert, XCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  donorContactService,
  type DonorContactRequestItem,
  type DonorPrivateContact,
} from "@/services/donors/donorContactService";

interface DonorContactModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  donorId: number;
  bloodGroup: string;
}

export function DonorContactModal({
  open,
  onOpenChange,
  donorId,
  bloodGroup,
}: DonorContactModalProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [reason, setReason] = useState<string>("");
  const [existingRequest, setExistingRequest] = useState<DonorContactRequestItem | null>(null);
  const [contactDetails, setContactDetails] = useState<DonorPrivateContact | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkStatusAndDetails = async () => {
    if (!open || !donorId) return;
    setLoading(true);
    setError(null);
    setContactDetails(null);
    setExistingRequest(null);

    try {
      // 1. Check if user already has an approved or pending request for this donor
      const requests = await donorContactService.getContactRequests({ view_as: "requester" });
      const currentReq = requests.find((r) => r.donor_id === donorId);
      if (currentReq) {
        setExistingRequest(currentReq);
        if (currentReq.status === "APPROVED") {
          // Fetch full contact details
          const details = await donorContactService.getDonorContactDetails(donorId);
          setContactDetails(details);
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      checkStatusAndDetails();
    }
  }, [open, donorId]);

  const handleSubmitRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) {
      setError("Please provide a valid clinical or emergency justification.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const created = await donorContactService.createContactRequest(donorId, reason.trim());
      setExistingRequest(created);
      toast.success("Contact request sent to donor! They will be notified to accept or decline.");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to send contact request.";
      setError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400">
              <Lock className="size-4" />
            </span>
            <div>
              <DialogTitle>Donor Contact Details</DialogTitle>
              <DialogDescription>
                Donor #{donorId} · Blood Group <span className="font-bold text-rose-600">{bloodGroup}</span>
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {loading ? (
          <div className="py-8 text-center">
            <Loader2 className="size-6 animate-spin text-primary mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">Checking consent authorization...</p>
          </div>
        ) : contactDetails ? (
          /* Approved State: Show full private contact details */
          <div className="space-y-4 py-3">
            <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
              <span>Consent Approved: You have explicit permission to access this donor's contact information.</span>
            </div>

            <div className="space-y-3 rounded-lg border bg-card p-4 text-sm">
              <div>
                <span className="text-xs text-muted-foreground">Full Name:</span>
                <p className="font-semibold text-foreground">{contactDetails.full_name || contactDetails.username}</p>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border">
                <div>
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Phone className="size-3" /> Phone Number:
                  </span>
                  <p className="font-mono text-sm font-bold text-foreground mt-0.5">
                    {contactDetails.phone || "Not provided"}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Mail className="size-3" /> Email Address:
                  </span>
                  <p className="text-sm font-medium text-foreground mt-0.5 break-all">
                    {contactDetails.email || "Not provided"}
                  </p>
                </div>
              </div>

              {contactDetails.address && (
                <div className="pt-2 border-t border-border">
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <MapPin className="size-3" /> Registered Location:
                  </span>
                  <p className="text-xs font-medium text-foreground mt-0.5">{contactDetails.address}</p>
                </div>
              )}
            </div>
          </div>
        ) : existingRequest?.status === "PENDING" ? (
          /* Pending State */
          <div className="space-y-4 py-4 text-center">
            <div className="rounded-full size-12 bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400 mx-auto flex items-center justify-center">
              <Clock className="size-6 animate-pulse" />
            </div>
            <div>
              <h4 className="font-semibold text-sm">Contact Request Pending</h4>
              <p className="text-xs text-muted-foreground mt-1 px-4">
                Your request submitted on{" "}
                {new Date(existingRequest.created_at).toLocaleDateString()} is awaiting approval by the donor.
                Private contact information is protected until approved.
              </p>
            </div>
            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200">
              Status: PENDING
            </Badge>
          </div>
        ) : existingRequest?.status === "DECLINED" ? (
          /* Declined State */
          <div className="space-y-4 py-4 text-center">
            <div className="rounded-full size-12 bg-destructive/10 text-destructive mx-auto flex items-center justify-center">
              <XCircle className="size-6" />
            </div>
            <div>
              <h4 className="font-semibold text-sm text-destructive">Contact Request Declined</h4>
              <p className="text-xs text-muted-foreground mt-1 px-4">
                The donor has declined access to their contact details. Private information remains protected.
              </p>
            </div>
            <Badge variant="outline" className="bg-destructive/10 text-destructive border-destructive/20">
              Status: DECLINED
            </Badge>
          </div>
        ) : (
          /* New Request Form */
          <form onSubmit={handleSubmitRequest} className="space-y-4 py-2">
            <div className="flex items-start gap-2 rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">
              <ShieldAlert className="size-4 shrink-0 text-primary mt-0.5" />
              <span>
                To protect donor privacy, contact details are private. Submit an explicit request with your clinical or
                emergency justification. The donor will receive an in-app notification to review.
              </span>
            </div>

            {error && (
              <div className="rounded-md bg-destructive/10 border border-destructive/20 p-2.5 text-xs text-destructive">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="req-reason" className="text-xs font-semibold">
                Clinical or Emergency Justification *
              </Label>
              <Textarea
                id="req-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Urgent requirement of 2 units of O+ blood for surgery at City Hospital..."
                rows={3}
                required
                className="text-xs"
              />
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={submitting || !reason.trim()}>
                {submitting ? (
                  <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                ) : (
                  <Send className="mr-1.5 size-3.5" />
                )}
                Submit Contact Request
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
