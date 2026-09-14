import { useEffect, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, Droplets, FlaskConical, PackageCheck, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { BloodGroupTile } from "@/components/common/BloodGroupTile";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { StatCard } from "@/components/common/StatCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardsSkeleton, EmptyState, TableSkeleton } from "@/components/common/StateBlocks";
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
import { BLOOD_GROUPS, type BloodGroup } from "@/lib/types";
import { useAuth } from "@/providers/AuthProvider";
import { facilityService, type BloodBankFacility } from "@/services/facilities/facilityService";
import {
  inventoryService,
  type BloodStock,
  type BloodUnitItem,
} from "@/services/inventory/inventoryService";

function getTodayDateString(): string {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export const Route = createFileRoute("/app/inventory")({
  head: () => ({
    meta: [
      { title: "Blood Inventory — Blood Management System" },
      {
        name: "description",
        content: "Track blood units by group, status and expiry across the blood bank inventory.",
      },
      { property: "og:title", content: "Blood Inventory — Blood Management System" },
      { property: "og:description", content: "Track blood units by group, status and expiry." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: InventoryPage,
});

function InventoryPage() {
  const { user } = useAuth();
  const canAddUnit = user?.role === "SUPER_ADMIN" || user?.role === "BLOOD_BANK_ADMIN";

  const [stock, setStock] = useState<BloodStock[]>([]);
  const [units, setUnits] = useState<BloodUnitItem[]>([]);
  const [loadingStock, setLoadingStock] = useState(true);
  const [loadingUnits, setLoadingUnits] = useState(true);

  // Add Blood Unit Modal State
  const [addOpen, setAddOpen] = useState(false);
  const [bloodBanks, setBloodBanks] = useState<BloodBankFacility[]>([]);
  const [selectedBankId, setSelectedBankId] = useState<string>("");
  const [selectedGroup, setSelectedGroup] = useState<BloodGroup>("O+");
  const [collectionDate, setCollectionDate] = useState<string>(() => getTodayDateString());
  const [unitId, setUnitId] = useState<string>("");
  const [addingUnit, setAddingUnit] = useState(false);

  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("ALL");
  const [status, setStatus] = useState("ALL");

  const loadData = async () => {
    setLoadingStock(true);
    setLoadingUnits(true);
    try {
      const [stockData, unitData] = await Promise.all([
        inventoryService.getStock(),
        inventoryService.listUnits(),
      ]);
      setStock(stockData);
      setUnits(unitData);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load inventory data.");
    } finally {
      setLoadingStock(false);
      setLoadingUnits(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (canAddUnit) {
      facilityService
        .getBloodBanks({ status: "active" })
        .then((banks) => {
          setBloodBanks(banks);
          if (banks.length > 0 && !selectedBankId) {
            const firstBank = banks[0];
            if (firstBank) {
              setSelectedBankId(String(firstBank.id));
            }
          }
        })
        .catch(() => {
          // fallback
        });
    }
  }, [canAddUnit]);

  const handleAddUnit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedBankId) {
      toast.error("Please select a blood bank facility.");
      return;
    }
    if (!selectedGroup) {
      toast.error("Please select a blood group.");
      return;
    }
    if (!collectionDate) {
      toast.error("Please provide a collection date.");
      return;
    }
    const todayStr = getTodayDateString();
    if (collectionDate > todayStr) {
      toast.error("Collection date cannot be in the future.");
      return;
    }

    setAddingUnit(true);
    try {
      const newUnit = await inventoryService.createUnit({
        blood_bank: Number(selectedBankId),
        blood_group: selectedGroup,
        collection_date: collectionDate,
        unit_id: unitId.trim() || undefined,
      });
      toast.success(
        `Blood unit ${newUnit.unit_id} registered successfully and queued for laboratory testing (Status: TESTING).`,
      );
      setAddOpen(false);
      setUnitId("");
      setCollectionDate(getTodayDateString());
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Failed to create blood unit.");
    } finally {
      setAddingUnit(false);
    }
  };

  const filtered = useMemo(
    () =>
      units.filter(
        (u) =>
          (group === "ALL" || u.group === group) &&
          (status === "ALL" || u.status === status) &&
          (u.id.toLowerCase().includes(query.toLowerCase()) ||
            u.bank.toLowerCase().includes(query.toLowerCase()) ||
            u.donorName.toLowerCase().includes(query.toLowerCase())),
      ),
    [units, group, status, query],
  );

  const totalUnits = stock.reduce((s, x) => s + x.units, 0);
  const lowStock = stock.filter((s) => s.units < s.threshold);
  const expiringSoon = units.filter(
    (u) =>
      u.status === "AVAILABLE" &&
      new Date(u.expiresAt).getTime() - Date.now() < 1000 * 60 * 60 * 24 * 10 &&
      new Date(u.expiresAt).getTime() > Date.now(),
  );

  return (
    <DashboardLayout title="Inventory">
      <PageHeader
        title="Blood inventory"
        description="Group-wise stock levels, safety thresholds, and individual unit traceability."
        actions={
          canAddUnit ? (
            <Dialog open={addOpen} onOpenChange={setAddOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="mr-2 size-4" /> Add Blood Unit
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <form onSubmit={handleAddUnit}>
                  <DialogHeader>
                    <DialogTitle>Add blood unit</DialogTitle>
                    <DialogDescription>
                      Register a newly collected blood unit. Units enter the laboratory quality testing queue in TESTING status.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label htmlFor="unit-bank">Blood Bank Facility</Label>
                      <Select
                        value={selectedBankId}
                        onValueChange={setSelectedBankId}
                        disabled={bloodBanks.length <= 1 && user?.role === "BLOOD_BANK_ADMIN"}
                      >
                        <SelectTrigger id="unit-bank">
                          <SelectValue placeholder="Select Blood Bank" />
                        </SelectTrigger>
                        <SelectContent>
                          {bloodBanks.map((b) => (
                            <SelectItem key={b.id} value={String(b.id)}>
                              {b.name} ({b.city}, {b.state})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="unit-group">Blood Group</Label>
                      <Select
                        value={selectedGroup}
                        onValueChange={(val) => setSelectedGroup(val as BloodGroup)}
                      >
                        <SelectTrigger id="unit-group">
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
                    <div className="space-y-2">
                      <Label htmlFor="unit-date">Collection Date</Label>
                      <Input
                        id="unit-date"
                        type="date"
                        max={new Date().toISOString().split("T")[0]}
                        value={collectionDate}
                        onChange={(e) => setCollectionDate(e.target.value)}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="unit-id">Unit Identifier (Optional)</Label>
                      <Input
                        id="unit-id"
                        placeholder="e.g. BU-20260914-001 (auto-generated if empty)"
                        value={unitId}
                        onChange={(e) => setUnitId(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        Leave blank to auto-generate a unique system identifier.
                      </p>
                    </div>
                    <div className="rounded-lg border bg-muted/40 p-3 text-xs text-muted-foreground space-y-1">
                      <div className="flex items-center font-medium text-foreground">
                        <FlaskConical className="mr-1.5 size-3.5 text-primary" />
                        Quality Assurance & Expiry
                      </div>
                      <p>
                        • Initial status is strictly set to <strong>TESTING</strong> until cleared by Lab Technician screening.
                      </p>
                      <p>
                        • Expiry date is automatically calculated as <strong>Collection Date + 42 days</strong>.
                      </p>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setAddOpen(false)}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" disabled={addingUnit}>
                      {addingUnit ? "Registering..." : "Add Blood Unit"}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          ) : undefined
        }
      />

      {loadingStock ? (
        <CardsSkeleton count={3} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Total available units" value={totalUnits} icon={Droplets} />
          <StatCard
            label="Low stock groups"
            value={lowStock.length}
            icon={AlertTriangle}
            {...(lowStock.length > 0 ? { tone: "danger" as const } : {})}
            hint={lowStock.map((s) => s.group).join(", ") || "All groups adequate"}
          />
          <StatCard
            label="Expiring in 10 days"
            value={expiringSoon.length}
            icon={PackageCheck}
            {...(expiringSoon.length > 0 ? { tone: "warning" as const } : {})}
          />
        </div>
      )}

      <SectionCard
        title="Group-wise stock"
        description="Live available inventory count per blood group across blood bank facilities"
      >
        {loadingStock ? (
          <CardsSkeleton count={8} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {stock.map((s) => (
              <BloodGroupTile
                key={s.group}
                group={s.group}
                units={s.units}
                level={s.units >= s.threshold * 2 ? "HIGH" : s.units >= s.threshold ? "MODERATE" : "LOW"}
              />
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Blood units"
        description="Traceability record of every collected unit with lifecycle status"
        bodyClassName="p-0"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="w-48 pl-9"
                placeholder="Unit ID or facility"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search units"
              />
            </div>
            <Select value={group} onValueChange={setGroup}>
              <SelectTrigger className="w-28" aria-label="Filter by group">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All groups</SelectItem>
                {BLOOD_GROUPS.map((g) => (
                  <SelectItem key={g} value={g}>
                    {g}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-36" aria-label="Filter by status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All statuses</SelectItem>
                <SelectItem value="TESTING">Testing</SelectItem>
                <SelectItem value="AVAILABLE">Available</SelectItem>
                <SelectItem value="RESERVED">Reserved</SelectItem>
                <SelectItem value="DISPATCHED">Dispatched</SelectItem>
                <SelectItem value="DISCARDED">Discarded</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      >
        {loadingUnits ? (
          <TableSkeleton cols={6} />
        ) : filtered.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title="No units match these filters"
              description="Try clearing the search query or selecting a different blood group / status."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Unit ID</TableHead>
                <TableHead>Group</TableHead>
                <TableHead>Facility</TableHead>
                <TableHead>Collected</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-mono text-xs">{u.id}</TableCell>
                  <TableCell className="font-bold text-primary">{u.group}</TableCell>
                  <TableCell className="font-medium">{u.bank}</TableCell>
                  <TableCell>{u.collectedAt ? new Date(u.collectedAt).toLocaleDateString() : "-"}</TableCell>
                  <TableCell>
                    {u.expiresAt ? (
                      <span className={u.isExpired ? "text-destructive font-semibold" : ""}>
                        {new Date(u.expiresAt).toLocaleDateString()}
                        {u.isExpired ? " (Expired)" : ""}
                      </span>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={u.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>
    </DashboardLayout>
  );
}
