import { useEffect, useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { CheckCircle2, HeartHandshake, Loader2, MapPin, Phone, Mail, Plus, Shield, Users, XCircle } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { EmptyState, TableSkeleton } from "@/components/common/StateBlocks";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { BLOOD_GROUPS, type BloodGroup, type BloodRequest, type Urgency } from "@/lib/types";
import { useAuth } from "@/providers/AuthProvider";
import { requestService, type BloodBankOption, type DonorContactResponse } from "@/services/requests/requestService";

export const Route = createFileRoute("/app/requests")({
  head: () => ({
    meta: [
      { title: "Blood Requests — Blood Management System" },
      {
        name: "description",
        content: "Raise, review and approve hospital blood requests with urgency-based prioritisation.",
      },
      { property: "og:title", content: "Blood Requests — Blood Management System" },
      { property: "og:description", content: "Raise, review and approve hospital blood requests." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: RequestsPage,
});

function RequestsPage() {
  const { user } = useAuth();
  const [requests, setRequests] = useState<BloodRequest[]>([]);
  const [bloodBanks, setBloodBanks] = useState<BloodBankOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [tab, setTab] = useState("ALL");

  const [decision, setDecision] = useState<{ id: string; status: "APPROVED" | "REJECTED" } | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  // Donor Response State
  const [donorTargetRequest, setDonorTargetRequest] = useState<BloodRequest | null>(null);
  const [donorNotes, setDonorNotes] = useState("");
  const [donorResponding, setDonorResponding] = useState(false);

  // Hospital Staff View Responses State
  const [responsesTargetRequest, setResponsesTargetRequest] = useState<BloodRequest | null>(null);
  const [responsesList, setResponsesList] = useState<DonorContactResponse[]>([]);
  const [responsesLoading, setResponsesLoading] = useState(false);

  // Hospital Staff Outcome Recording State
  const [outcomeConfirm, setOutcomeConfirm] = useState<{
    response: DonorContactResponse;
    outcome: "COMPLETED" | "DID_NOT_HAPPEN";
  } | null>(null);
  const [outcomeNotes, setOutcomeNotes] = useState("");
  const [recordingOutcome, setRecordingOutcome] = useState(false);

  const handleRecordOutcome = async () => {
    if (!outcomeConfirm || !responsesTargetRequest) return;
    setRecordingOutcome(true);
    try {
      await requestService.recordOutcome(responsesTargetRequest.id, outcomeConfirm.response.id, {
        outcome: outcomeConfirm.outcome,
        notes: outcomeNotes,
      });
      toast.success(
        outcomeConfirm.outcome === "COMPLETED"
          ? "Donation marked as completed successfully."
          : "Recorded that donation did not take place."
      );
      setOutcomeConfirm(null);
      setOutcomeNotes("");
      // Refresh responses list
      const updated = await requestService.listResponses(responsesTargetRequest.id);
      setResponsesList(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to record donation outcome.");
    } finally {
      setRecordingOutcome(false);
    }
  };

  // New Request Form State
  const [newRequest, setNewRequest] = useState<{
    bloodBankId: string;
    bloodGroup: BloodGroup;
    units: number;
    urgency: Urgency;
  }>({
    bloodBankId: "",
    bloodGroup: "O+",
    units: 2,
    urgency: "NORMAL",
  });

  const isDonor = user?.role === "DONOR";
  const isHospital = user?.role === "HOSPITAL_STAFF";
  const isBloodBankAdmin = user?.role === "BLOOD_BANK_ADMIN" || user?.role === "SUPER_ADMIN";

  const loadRequests = async () => {
    setLoading(true);
    try {
      const data = await requestService.list();
      setRequests(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load blood requests.");
    } finally {
      setLoading(false);
    }
  };

  const loadBloodBanks = async () => {
    try {
      const banks = await requestService.listBloodBanks();
      setBloodBanks(banks);
      if (banks.length > 0) {
        const firstBank = banks[0];
        if (firstBank) {
          setNewRequest((prev) => ({ ...prev, bloodBankId: String(firstBank.id) }));
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load blood bank facilities.");
    }
  };

  useEffect(() => {
    loadRequests();
    if (!isDonor) {
      loadBloodBanks();
    }
  }, [isDonor]);

  const filtered = useMemo(
    () => (tab === "ALL" ? requests : requests.filter((r) => r.status === tab)),
    [requests, tab],
  );

  const handleCreateRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRequest.bloodBankId) {
      toast.error("Please select a target blood bank facility.");
      return;
    }

    setSubmitting(true);
    try {
      await requestService.create({
        blood_bank: parseInt(newRequest.bloodBankId, 10),
        blood_group: newRequest.bloodGroup,
        units_needed: newRequest.units,
        urgency: newRequest.urgency,
      });

      toast.success("Blood request submitted successfully.");
      setCreateOpen(false);
      await loadRequests();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create blood request.");
    } finally {
      setSubmitting(false);
    }
  };

  const applyDecision = async () => {
    if (!decision) return;

    setSubmitting(true);
    try {
      if (decision.status === "APPROVED") {
        await requestService.approve(decision.id);
        toast.success(`Request ${decision.id} approved. Matching units reserved.`);
      } else {
        if (!rejectionReason.trim()) {
          toast.error("Please provide a rejection explanation.");
          setSubmitting(false);
          return;
        }
        await requestService.reject(decision.id, rejectionReason.trim());
        toast.success(`Request ${decision.id} rejected.`);
      }

      setDecision(null);
      setRejectionReason("");
      await loadRequests();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update request.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDonorResponse = async (action: "ACCEPT" | "DECLINE") => {
    if (!donorTargetRequest) return;
    setDonorResponding(true);
    try {
      await requestService.respond(donorTargetRequest.id, action, donorNotes.trim());
      if (action === "ACCEPT") {
        toast.success("Accepted. Your permitted contact details have been shared with the requesting hospital.");
      } else {
        toast.info("Declined. Your contact details were not shared.");
      }
      setDonorTargetRequest(null);
      setDonorNotes("");
      await loadRequests();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to respond to blood request.");
    } finally {
      setDonorResponding(false);
    }
  };

  const openResponsesDialog = async (r: BloodRequest) => {
    setResponsesTargetRequest(r);
    setResponsesLoading(true);
    try {
      const list = await requestService.listResponses(r.id);
      setResponsesList(list);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load donor responses.");
      setResponsesList([]);
    } finally {
      setResponsesLoading(false);
    }
  };

  return (
    <DashboardLayout title="Blood Requests">
      <PageHeader
        title={
          isDonor
            ? "Active Blood Requests"
            : isHospital
              ? "My blood requests"
              : "Incoming blood requests"
        }
        description={
          isDonor
            ? "Review emergency and scheduled blood requirements from local healthcare facilities and choose whether to respond."
            : isHospital
              ? "Raise new requests, review donor responses, and follow real-time reservation status."
              : "Review clinical demand and approve reservations against available non-expired stock."
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" asChild>
              <Link to="/app/map">
                <MapPin className="size-4 mr-1.5" /> Nearby Resources
              </Link>
            </Button>
            {isHospital ? (
              <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <Plus className="size-4 mr-1.5" /> New request
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Raise a blood request</DialogTitle>
                    <DialogDescription>
                      Submit an emergency or scheduled blood request to a designated blood bank facility.
                    </DialogDescription>
                  </DialogHeader>

                  <form className="grid gap-4" onSubmit={handleCreateRequest}>
                    <div className="grid gap-2">
                      <Label htmlFor="target-bank">Target Blood Bank Facility</Label>
                      <Select
                        value={newRequest.bloodBankId}
                        onValueChange={(val) => setNewRequest({ ...newRequest, bloodBankId: val })}
                      >
                        <SelectTrigger id="target-bank">
                          <SelectValue placeholder="Select target facility" />
                        </SelectTrigger>
                        <SelectContent>
                          {bloodBanks.length === 0 ? (
                            <SelectItem value="none" disabled>
                              No active blood banks available
                            </SelectItem>
                          ) : (
                            bloodBanks.map((bank) => (
                              <SelectItem key={bank.id} value={String(bank.id)}>
                                {bank.name} ({bank.city}, {bank.state})
                              </SelectItem>
                            ))
                          )}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="grid gap-2">
                        <Label htmlFor="req-group">Blood group</Label>
                        <Select
                          value={newRequest.bloodGroup}
                          onValueChange={(val) => setNewRequest({ ...newRequest, bloodGroup: val as BloodGroup })}
                        >
                          <SelectTrigger id="req-group">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {BLOOD_GROUPS.map((g) => (
                              <SelectItem key={g} value={g}>
                                {g}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="req-units">Units Needed</Label>
                        <Input
                          id="req-units"
                          type="number"
                          min={1}
                          max={50}
                          value={newRequest.units}
                          onChange={(e) =>
                            setNewRequest({ ...newRequest, units: Math.max(1, parseInt(e.target.value, 10) || 1) })
                          }
                          required
                        />
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <Label htmlFor="req-urgency">Clinical Urgency</Label>
                      <Select
                        value={newRequest.urgency}
                        onValueChange={(val) => setNewRequest({ ...newRequest, urgency: val as Urgency })}
                      >
                        <SelectTrigger id="req-urgency">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="NORMAL">Normal</SelectItem>
                          <SelectItem value="HIGH">High</SelectItem>
                          <SelectItem value="CRITICAL">Critical / Emergency</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <DialogFooter>
                      <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                        Cancel
                      </Button>
                      <Button type="submit" disabled={submitting}>
                        {submitting ? <Loader2 className="size-4 animate-spin" /> : "Submit Request"}
                      </Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            ) : null}
          </div>
        }
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {["ALL", "PENDING", "APPROVED", "DISPATCHED", "COMPLETED", "REJECTED"].map((t) => (
            <TabsTrigger key={t} value={t}>
              {t === "ALL" ? "All" : t.charAt(0) + t.slice(1).toLowerCase()}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <SectionCard bodyClassName="p-0">
        {loading ? (
          <TableSkeleton cols={7} />
        ) : filtered.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title="No requests in this state"
              description={isDonor ? "No active blood requests currently matching this filter." : "Requests will appear here as hospitals submit them to blood banks."}
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Request</TableHead>
                <TableHead>Facility / Staff</TableHead>
                <TableHead>Group</TableHead>
                <TableHead>Units</TableHead>
                <TableHead>Urgency</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.id}</TableCell>
                  <TableCell className="font-medium">{r.hospital}</TableCell>
                  <TableCell className="font-bold text-primary">{r.group}</TableCell>
                  <TableCell>{r.units}</TableCell>
                  <TableCell>
                    <StatusBadge status={r.urgency} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {isDonor ? (
                        (r.status === "PENDING" || r.status === "APPROVED") ? (
                          <Button
                            size="sm"
                            onClick={() => {
                              setDonorTargetRequest(r);
                              setDonorNotes("");
                            }}
                          >
                            <HeartHandshake className="size-3.5 mr-1" /> Respond
                          </Button>
                        ) : (
                          <span className="text-xs text-muted-foreground">Closed</span>
                        )
                      ) : null}

                      {isHospital && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 px-2.5 text-xs"
                          onClick={() => openResponsesDialog(r)}
                        >
                          <Users className="size-3.5 mr-1" /> Donor Responses
                        </Button>
                      )}

                      {(isHospital || isBloodBankAdmin) && (
                        <Button size="sm" variant="ghost" className="h-8 px-2 text-xs" asChild>
                          <Link to="/app/map" search={{ blood_group: r.group, radius: 25 }}>
                            <MapPin className="size-3.5 mr-1" /> Donors
                          </Link>
                        </Button>
                      )}
                      {isBloodBankAdmin && (
                        r.status === "PENDING" ? (
                          <>
                            <Button
                              size="sm"
                              onClick={() => setDecision({ id: r.id, status: "APPROVED" })}
                            >
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setDecision({ id: r.id, status: "REJECTED" })}
                            >
                              Reject
                            </Button>
                          </>
                        ) : (
                          <span className="text-xs text-muted-foreground">Processed</span>
                        )
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      {/* Donor Respond Dialog */}
      <Dialog open={donorTargetRequest !== null} onOpenChange={(open) => !open && setDonorTargetRequest(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HeartHandshake className="size-5 text-primary" /> Respond to Blood Request {donorTargetRequest?.id}
            </DialogTitle>
            <DialogDescription>
              Review the requirement details and choose whether to accept or decline.
            </DialogDescription>
          </DialogHeader>

          {donorTargetRequest && (
            <div className="space-y-4 py-2 text-sm">
              <div className="grid grid-cols-2 gap-3 rounded-lg border bg-muted/40 p-3">
                <div>
                  <span className="text-xs text-muted-foreground">Blood Group Needed:</span>
                  <p className="font-bold text-base text-primary">{donorTargetRequest.group}</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Units Needed:</span>
                  <p className="font-semibold text-base">{donorTargetRequest.units} unit(s)</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Urgency:</span>
                  <p><StatusBadge status={donorTargetRequest.urgency} /></p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Requesting Facility:</span>
                  <p className="font-medium text-xs truncate">{donorTargetRequest.hospital}</p>
                </div>
              </div>

              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs leading-relaxed space-y-1.5">
                <div className="flex items-center gap-1.5 font-semibold text-primary">
                  <Shield className="size-4" /> Privacy & Consent Notice
                </div>
                <p>
                  <strong>Accepting</strong> explicitly grants consent to share your registered name, phone number, and email address with the requesting hospital so clinical staff can coordinate donation.
                </p>
                <p className="text-muted-foreground">
                  <strong>Declining</strong> ensures your contact details remain strictly confidential and will not be disclosed.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="donor-notes">Optional note to hospital staff</Label>
                <Textarea
                  id="donor-notes"
                  rows={2}
                  placeholder="e.g. Available today after 3 PM."
                  value={donorNotes}
                  onChange={(e) => setDonorNotes(e.target.value)}
                />
              </div>
            </div>
          )}

          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleDonorResponse("DECLINE")}
              disabled={donorResponding}
              className="text-muted-foreground hover:text-destructive"
            >
              {donorResponding ? <Loader2 className="size-4 animate-spin" /> : "Decline"}
            </Button>
            <Button
              type="button"
              onClick={() => handleDonorResponse("ACCEPT")}
              disabled={donorResponding}
            >
              {donorResponding ? <Loader2 className="size-4 animate-spin" /> : "Accept & Reveal My Details"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Hospital Staff Donor Responses Dialog */}
      <Dialog open={responsesTargetRequest !== null} onOpenChange={(open) => !open && setResponsesTargetRequest(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="size-5 text-primary" /> Donor Responses for {responsesTargetRequest?.id}
            </DialogTitle>
            <DialogDescription>
              Review all donor responses and view permitted contact details for accepted donors.
            </DialogDescription>
          </DialogHeader>

          {responsesLoading ? (
            <div className="py-8 flex justify-center">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : responsesList.length === 0 ? (
            <div className="py-6">
              <EmptyState
                icon={Users}
                title="No donor responses yet"
                description="When eligible donors view and respond to this request, their responses will appear here."
              />
            </div>
          ) : (
            <div className="space-y-3 py-2">
              {responsesList.map((resp) => {
                const isAccepted = resp.status === "APPROVED";
                return (
                  <div
                    key={resp.id}
                    className={`rounded-lg border p-4 transition-colors ${
                      isAccepted ? "border-green-500/30 bg-green-500/5" : "border-border bg-muted/20"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">
                            {resp.contact_details?.name || resp.donor_display}
                          </span>
                          <span className="rounded bg-primary/10 px-2 py-0.5 text-xs font-bold text-primary">
                            {resp.donor_blood_group || resp.blood_group}
                          </span>
                        </div>
                        {resp.message && (
                          <p className="text-xs text-muted-foreground italic">"{resp.message}"</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {isAccepted ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                            <CheckCircle2 className="size-3.5" /> Accepted
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2.5 py-0.5 text-xs font-medium text-destructive">
                            <XCircle className="size-3.5" /> Declined
                          </span>
                        )}
                      </div>
                    </div>

                    {isAccepted && resp.contact_details ? (
                      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 rounded bg-background/80 p-2.5 border text-xs">
                        <div className="flex items-center gap-1.5">
                          <Phone className="size-3.5 text-primary" />
                          <span className="font-mono">{resp.contact_details.phone || "No phone provided"}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Mail className="size-3.5 text-primary" />
                          <span className="font-mono truncate">{resp.contact_details.email}</span>
                        </div>
                      </div>
                    ) : !isAccepted ? (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Donor declined this request. Contact details are not accessible.
                      </p>
                    ) : null}

                    {/* Outcome Status / Actions */}
                    {isAccepted && (
                      <div className="mt-3 pt-3 border-t border-border/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="text-xs">
                          {resp.donation_outcome === "COMPLETED" ? (
                            <div className="space-y-0.5">
                              <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 dark:text-emerald-400">
                                <CheckCircle2 className="size-3.5" /> Donation Completed
                              </span>
                              {resp.outcome_recorded_at && (
                                <p className="text-[11px] text-muted-foreground">
                                  Recorded on {new Date(resp.outcome_recorded_at).toLocaleDateString()}
                                  {resp.outcome_recorded_by_name ? ` by ${resp.outcome_recorded_by_name}` : ""}
                                </p>
                              )}
                              {resp.outcome_notes && (
                                <p className="text-[11px] text-muted-foreground italic">"{resp.outcome_notes}"</p>
                              )}
                            </div>
                          ) : resp.donation_outcome === "DID_NOT_HAPPEN" ? (
                            <div className="space-y-0.5">
                              <span className="inline-flex items-center gap-1 font-semibold text-amber-600 dark:text-amber-400">
                                <XCircle className="size-3.5" /> Donation Did Not Happen
                              </span>
                              {resp.outcome_recorded_at && (
                                <p className="text-[11px] text-muted-foreground">
                                  Recorded on {new Date(resp.outcome_recorded_at).toLocaleDateString()}
                                  {resp.outcome_recorded_by_name ? ` by ${resp.outcome_recorded_by_name}` : ""}
                                </p>
                              )}
                              {resp.outcome_notes && (
                                <p className="text-[11px] text-muted-foreground italic">"{resp.outcome_notes}"</p>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              Outcome not recorded yet.
                            </span>
                          )}
                        </div>

                        {/* Outcome action buttons for hospital staff */}
                        {isHospital && (!resp.donation_outcome || resp.donation_outcome === "NOT_RECORDED") && (
                          <div className="flex items-center gap-2 shrink-0">
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 text-xs border-emerald-500/30 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10"
                              onClick={() => {
                                setOutcomeConfirm({ response: resp, outcome: "COMPLETED" });
                                setOutcomeNotes("");
                              }}
                            >
                              <CheckCircle2 className="size-3 mr-1" />
                              Donation Completed
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 text-xs border-amber-500/30 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10"
                              onClick={() => {
                                setOutcomeConfirm({ response: resp, outcome: "DID_NOT_HAPPEN" });
                                setOutcomeNotes("");
                              }}
                            >
                              <XCircle className="size-3 mr-1" />
                              Did Not Happen
                            </Button>
                          </div>
                        )}
                      </div>
                    )}

                    {resp.responded_at && (
                      <p className="mt-2 text-[11px] text-muted-foreground">
                        Responded on {new Date(resp.responded_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setResponsesTargetRequest(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Donation Outcome Confirm Dialog */}
      <ConfirmDialog
        open={outcomeConfirm !== null}
        onOpenChange={(open) => {
          if (!open) {
            setOutcomeConfirm(null);
            setOutcomeNotes("");
          }
        }}
        title={
          outcomeConfirm?.outcome === "COMPLETED"
            ? "Record Donation Completed?"
            : "Record Donation Did Not Happen?"
        }
        description={
          outcomeConfirm?.outcome === "COMPLETED"
            ? `This will record that ${outcomeConfirm?.response?.contact_details?.name || outcomeConfirm?.response?.donor_display} successfully completed their blood donation for this request.`
            : `This will record that the blood donation with ${outcomeConfirm?.response?.contact_details?.name || outcomeConfirm?.response?.donor_display} did not take place.`
        }
        confirmLabel={
          recordingOutcome
            ? "Saving..."
            : outcomeConfirm?.outcome === "COMPLETED"
            ? "Confirm Completed"
            : "Confirm Did Not Happen"
        }
        destructive={outcomeConfirm?.outcome === "DID_NOT_HAPPEN"}
        onConfirm={handleRecordOutcome}
      >
        <div className="mt-3 space-y-2 text-left">
          <Label htmlFor="outcome-notes">Clinical / Operational Notes (Optional)</Label>
          <Textarea
            id="outcome-notes"
            rows={2}
            placeholder={
              outcomeConfirm?.outcome === "COMPLETED"
                ? "e.g. 1 unit whole blood collected, donor in good health."
                : "e.g. Donor was unable to attend due to personal conflict."
            }
            value={outcomeNotes}
            onChange={(e) => setOutcomeNotes(e.target.value)}
          />
        </div>
      </ConfirmDialog>

      {/* Decision Dialog */}
      <ConfirmDialog
        open={decision !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDecision(null);
            setRejectionReason("");
          }
        }}
        title={decision?.status === "APPROVED" ? "Approve this blood request?" : "Reject this blood request?"}
        description={
          decision?.status === "APPROVED"
            ? "Approving this request will atomically reserve matching non-expired units from the blood bank inventory."
            : "Please provide an explanation for rejecting this request."
        }
        confirmLabel={decision?.status === "APPROVED" ? "Confirm Approval" : "Confirm Rejection"}
        destructive={decision?.status === "REJECTED"}
        onConfirm={applyDecision}
      >
        {decision?.status === "REJECTED" ? (
          <div className="mt-3 space-y-2 text-left">
            <Label htmlFor="rej-reason">Rejection reason *</Label>
            <Textarea
              id="rej-reason"
              rows={3}
              placeholder="e.g. Insufficient stock of requested blood group at this time."
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              required
            />
          </div>
        ) : null}
      </ConfirmDialog>
    </DashboardLayout>
  );
}
