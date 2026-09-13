import { useEffect, useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Loader2, MapPin, Plus } from "lucide-react";
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
import { requestService, type BloodBankOption } from "@/services/requests/requestService";

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
    loadBloodBanks();
  }, []);

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

  return (
    <DashboardLayout title="Blood Requests">
      <PageHeader
        title={isHospital ? "My blood requests" : "Incoming blood requests"}
        description={
          isHospital
            ? "Raise new requests and follow their real-time approval and dispatch status."
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
              description="Requests will appear here as hospitals submit them to blood banks."
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
